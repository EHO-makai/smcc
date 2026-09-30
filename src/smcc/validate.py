"""Snapshot validation for a .smcc/ sidecar (DEC-012).

Checks snapshot-establishable properties only: schema validity, unique IDs,
resolvable references and task dependencies, DAG acyclicity, stored-status
consistency with the dependency DAG, and context provenance structure.
Version-increment enforcement belongs to state-transition code, not here.

Every invariant has its own issue code so failures are individually
reportable (TASK-002 acceptance criteria).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from smcc.errors import SMCCError, SMCCFileError, SMCCValidationError
from smcc.models import (
    AnySMCCObject,
    Goal,
    ProjectConfig,
    Proposal,
    ProposalOperation,
    ProposalStatus,
    Result,
    StateObject,
    Task,
    TaskStatus,
)
from smcc.store import Store, _load_yaml, parse_object

# issue codes, one per invariant
SCHEMA = "schema"  # file unreadable, bad YAML, or fails the Pydantic schema
LOCATION = "location"  # object of the wrong kind for the directory it sits in
DUPLICATE_ID = "duplicate-id"  # same object id defined more than once
DANGLING_REF = "dangling-ref"  # reference to an id that does not exist
DEPENDENCY_CYCLE = "dependency-cycle"  # task_dependencies DAG has a cycle
STATUS_DEPENDENCY = "status-dependency"  # stored ready/blocked disagrees with the DAG
ACCEPTED_RESULT = "accepted-result"  # accepted_result does not resolve to a matching Result
PROVENANCE = "provenance"  # Result provenance structure is inconsistent


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    path: Path | None = None
    object_id: str | None = None

    def render(self) -> str:
        where = self.object_id or (str(self.path) if self.path else "<repository>")
        return f"[{self.code}] {where}: {self.message}"


@dataclass
class ValidationReport:
    smcc_dir: Path
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


@dataclass
class _Loaded:
    project: ProjectConfig | None = None
    # (file path, parsed object) for everything that parsed successfully
    objects: list[tuple[Path, AnySMCCObject]] = field(default_factory=list)


def _load_lenient(store: Store, issues: list[Issue]) -> _Loaded:
    """Load everything that parses, collecting an issue per failure instead of
    stopping at the first bad file (unlike Store.load_all)."""
    loaded = _Loaded()

    project_path = store.smcc_dir / "project.yaml"
    try:
        loaded.project = store.load_project()
    except (SMCCFileError, SMCCValidationError) as exc:
        issues.append(Issue(SCHEMA, str(exc), path=project_path))

    expected_kind: list[tuple[Path, type, str]] = [
        (store.smcc_dir / "state", StateObject, "an authoritative state object"),
        (store.smcc_dir / "proposals", Proposal, "a Proposal"),
    ]
    for directory, kind, label in expected_kind:
        for path in store._data_files(directory):
            _parse_into(loaded, issues, path, kind, label)

    tasks_dir = store.smcc_dir / "tasks"
    if tasks_dir.is_dir():
        for task_file in sorted(tasks_dir.glob("*/task.yaml")):
            _parse_into(loaded, issues, task_file, Task, "a Task")
        for path in sorted(tasks_dir.glob("*/results/*")):
            if path.is_file() and path.suffix in {".yaml", ".yml"}:
                _parse_into(loaded, issues, path, Result, "a Result")
    return loaded


def _parse_into(
    loaded: _Loaded, issues: list[Issue], path: Path, kind: type, label: str
) -> None:
    try:
        obj = parse_object(_load_yaml(path), path)
    except SMCCError as exc:
        issues.append(Issue(SCHEMA, str(exc), path=path))
        return
    if not isinstance(obj, kind):
        issues.append(
            Issue(LOCATION, f"expected {label} here, got type {obj.type!r}", path=path)
        )
        return
    loaded.objects.append((path, obj))


def _check_duplicate_ids(loaded: _Loaded, issues: list[Issue]) -> dict[str, AnySMCCObject]:
    by_id: dict[str, AnySMCCObject] = {}
    seen_paths: dict[str, Path] = {}
    for path, obj in loaded.objects:
        if obj.id in by_id:
            issues.append(
                Issue(
                    DUPLICATE_ID,
                    f"id also defined in {seen_paths[obj.id]}",
                    path=path,
                    object_id=obj.id,
                )
            )
        else:
            by_id[obj.id] = obj
            seen_paths[obj.id] = path
    return by_id


def _check_references(
    loaded: _Loaded, by_id: dict[str, AnySMCCObject], issues: list[Issue]
) -> None:
    def require(owner: AnySMCCObject, field_name: str, ref: str) -> None:
        if ref not in by_id:
            issues.append(
                Issue(
                    DANGLING_REF,
                    f"{field_name} references unknown id {ref!r}",
                    object_id=owner.id,
                )
            )

    for _, obj in loaded.objects:
        # Result does not carry supersedes (immutable, DEC-007)
        for ref in getattr(obj, "supersedes", []):
            require(obj, "supersedes", ref)
        if isinstance(obj, Task):
            for ref in obj.task_dependencies:
                require(obj, "task_dependencies", ref)
            for ref in obj.context_refs:
                require(obj, "context_refs", ref)
            for ref in obj.constraints:
                require(obj, "constraints", ref)
        elif isinstance(obj, Result):
            require(obj, "task_id", obj.task_id)
        elif isinstance(obj, Proposal):
            if obj.operation in (ProposalOperation.update, ProposalOperation.supersede):
                require(obj, "target_id", obj.target_id)
            elif (
                obj.operation == ProposalOperation.create
                and obj.status == ProposalStatus.proposed
                and obj.target_id in by_id
            ):
                issues.append(
                    Issue(
                        DANGLING_REF,
                        f"create proposal targets id {obj.target_id!r} which already exists",
                        object_id=obj.id,
                    )
                )

    if loaded.project is not None:
        for ref in loaded.project.goal_refs:
            target = by_id.get(ref)
            if target is None:
                issues.append(
                    Issue(DANGLING_REF, f"project goal_refs references unknown id {ref!r}")
                )
            elif not isinstance(target, Goal):
                issues.append(
                    Issue(DANGLING_REF, f"project goal_refs {ref!r} is not a Goal")
                )


def _check_dependency_cycles(tasks: dict[str, Task], issues: list[Issue]) -> None:
    WHITE, GREY, BLACK = 0, 1, 2
    color = dict.fromkeys(tasks, WHITE)

    def visit(task_id: str, stack: list[str]) -> None:
        color[task_id] = GREY
        stack.append(task_id)
        for dep in tasks[task_id].task_dependencies:
            if dep not in tasks:
                continue  # dangling: reported by the reference check
            if color[dep] == GREY:
                cycle = stack[stack.index(dep) :] + [dep]
                issues.append(
                    Issue(
                        DEPENDENCY_CYCLE,
                        "task dependency cycle: " + " -> ".join(cycle),
                        object_id=dep,
                    )
                )
            elif color[dep] == WHITE:
                visit(dep, stack)
        stack.pop()
        color[task_id] = BLACK

    for task_id in sorted(tasks):
        if color[task_id] == WHITE:
            visit(task_id, [])


def _check_status_consistency(tasks: dict[str, Task], issues: list[Issue]) -> None:
    """Stored ready/blocked must agree with the dependency-derived state.

    A dependency is satisfied when the dependency task is accepted (its
    accepted_result is the dependency's output, ARCHITECTURE.md §8.2).
    """
    for task_id in sorted(tasks):
        task = tasks[task_id]
        unsatisfied = [
            dep
            for dep in task.task_dependencies
            if dep in tasks and tasks[dep].status != TaskStatus.accepted
        ]
        if task.status == TaskStatus.ready and unsatisfied:
            issues.append(
                Issue(
                    STATUS_DEPENDENCY,
                    f"status is 'ready' but dependencies are not accepted: {', '.join(unsatisfied)}",
                    object_id=task.id,
                )
            )
        elif task.status == TaskStatus.blocked and not unsatisfied:
            issues.append(
                Issue(
                    STATUS_DEPENDENCY,
                    "status is 'blocked' but every dependency is accepted",
                    object_id=task.id,
                )
            )


def _check_results(
    loaded: _Loaded, by_id: dict[str, AnySMCCObject], issues: list[Issue]
) -> None:
    tasks = {obj.id: obj for _, obj in loaded.objects if isinstance(obj, Task)}

    for task_id in sorted(tasks):
        task = tasks[task_id]
        if task.accepted_result is None:
            continue
        result = by_id.get(task.accepted_result)
        if not isinstance(result, Result):
            issues.append(
                Issue(
                    ACCEPTED_RESULT,
                    f"accepted_result {task.accepted_result!r} does not resolve to a Result",
                    object_id=task.id,
                )
            )
        elif result.task_id != task.id:
            issues.append(
                Issue(
                    ACCEPTED_RESULT,
                    f"accepted_result {result.id} belongs to {result.task_id}, not {task.id}",
                    object_id=task.id,
                )
            )

    for path, obj in loaded.objects:
        if isinstance(obj, Result):
            # tasks/<task_id>/results/<file> must match the Result's own task_id
            directory_task = path.parent.parent.name
            if directory_task != obj.task_id:
                issues.append(
                    Issue(
                        PROVENANCE,
                        f"stored under tasks/{directory_task}/ but task_id is {obj.task_id!r}",
                        path=path,
                        object_id=obj.id,
                    )
                )


def validate(smcc_dir: Path | str) -> ValidationReport:
    """Validate one sidecar directory and report every issue found."""
    smcc_dir = Path(smcc_dir)
    report = ValidationReport(smcc_dir=smcc_dir)
    try:
        store = Store(smcc_dir)
    except SMCCFileError as exc:
        report.issues.append(Issue(SCHEMA, str(exc), path=smcc_dir))
        return report

    loaded = _load_lenient(store, report.issues)
    by_id = _check_duplicate_ids(loaded, report.issues)
    _check_references(loaded, by_id, report.issues)
    tasks = {obj.id: obj for _, obj in loaded.objects if isinstance(obj, Task)}
    _check_dependency_cycles(tasks, report.issues)
    _check_status_consistency(tasks, report.issues)
    _check_results(loaded, by_id, report.issues)
    return report
