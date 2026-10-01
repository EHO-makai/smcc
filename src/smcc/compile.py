"""Deterministic context compiler (TASK-003).

Selection is explicit per CON-003 / ARCHITECTURE.md §9.1: the task itself, its
acceptance criteria and task-local constraints, the project goal, project-scoped
constraints, objects named by context_refs, and the accepted Result of each task
dependency. Output is a Markdown context package with YAML provenance
frontmatter (§9.3); content_hash excludes volatile fields (§9.4); compiled
contexts are content-addressed under .smcc/contexts/ and committed (§9.5).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from smcc.errors import SMCCError
from smcc.models import (
    Constraint,
    Decision,
    Finding,
    Goal,
    Question,
    Requirement,
    Result,
    StateObject,
    StateStatus,
    Task,
)
from smcc.store import Snapshot

COMPILER_VERSION = "0.1"


class CompileError(SMCCError):
    """The selection set for a task cannot be resolved into a compiled context."""


@dataclass(frozen=True)
class CompiledContext:
    """One compiled Markdown context package plus its provenance."""

    task_id: str
    task_version: int
    compiler_version: str
    # (id, version) of every authoritative state object consumed (DEC-004)
    state_refs: tuple[tuple[str, int], ...]
    # (dependency task_id, result_id) for each accepted dependency output
    dependency_results: tuple[tuple[str, str], ...]
    content_hash: str
    compiled_at: str
    body: str
    document: str


def _resolve_task(snapshot: Snapshot, task_id: str) -> Task:
    for task in snapshot.tasks:
        if task.id == task_id:
            return task
    raise CompileError(f"{task_id}: task not found")


def _select(snapshot: Snapshot, task: Task) -> tuple[dict[str, StateObject], list[Result]]:
    """Resolve the explicit selection set (CON-003). Deduped by object id."""
    objects = snapshot.by_id()
    selected: dict[str, StateObject] = {}

    def include_state(ref: str, requirer: str) -> None:
        obj = objects.get(ref)
        if obj is None:
            raise CompileError(f"{task.id}: {requirer} references unknown object {ref!r}")
        if not isinstance(obj, StateObject):
            raise CompileError(
                f"{task.id}: {requirer} reference {ref!r} is a {obj.type}, "
                "not an authoritative state object"
            )
        selected.setdefault(obj.id, obj)

    # project goal(s)
    for ref in snapshot.project.goal_refs:
        include_state(ref, "project.yaml goal_refs")

    # project-scoped constraints are always included (§9.1); retired ones are not
    # authoritative and are excluded unless explicitly named by the task
    for obj in snapshot.state_objects:
        if isinstance(obj, Constraint) and obj.scope == "project":
            if obj.status != StateStatus.retired:
                selected.setdefault(obj.id, obj)

    # task-local constraints and explicit context_refs
    for ref in task.constraints:
        include_state(ref, "constraints")
    for ref in task.context_refs:
        include_state(ref, "context_refs")

    # accepted Result of each task dependency, named by accepted_result (§8.2)
    dependency_results: list[Result] = []
    for dep_id in sorted(task.task_dependencies):
        dep = objects.get(dep_id)
        if dep is None or not isinstance(dep, Task):
            raise CompileError(f"{task.id}: task_dependencies references unknown task {dep_id!r}")
        if dep.accepted_result is None:
            raise CompileError(
                f"{task.id}: dependency {dep_id} has no accepted result; cannot compile"
            )
        result = objects.get(dep.accepted_result)
        if not isinstance(result, Result):
            raise CompileError(
                f"{task.id}: dependency {dep_id} names missing result {dep.accepted_result!r}"
            )
        dependency_results.append(result)

    return selected, dependency_results


# §9.2 section headings, in output order, keyed by state type
_STATE_SECTIONS: tuple[tuple[str, type], ...] = (
    ("Project Goal", Goal),
    ("Relevant Requirements", Requirement),
    ("Relevant Constraints", Constraint),
    ("Relevant Decisions", Decision),
    ("Known Findings", Finding),
    ("Open Questions", Question),
)


def _render_body(task: Task, selected: dict[str, StateObject], results: list[Result]) -> str:
    lines: list[str] = [f"# SMCC Context: {task.id}", ""]

    lines += ["## Task", "", f"{task.id} (v{task.version}) — {task.title}", ""]
    lines += ["## Goal", "", task.goal.strip(), ""]

    if task.acceptance_criteria:
        lines += ["## Acceptance Criteria", ""]
        lines += [f"- {criterion}" for criterion in task.acceptance_criteria]
        lines.append("")

    for heading, state_type in _STATE_SECTIONS:
        members = sorted(
            (obj for obj in selected.values() if isinstance(obj, state_type)),
            key=lambda obj: obj.id,
        )
        if not members:
            continue  # empty headings are omitted (§9.2)
        lines += [f"## {heading}", ""]
        for obj in members:
            lines += [f"### {obj.id} (v{obj.version}) — {obj.title}", "", obj.statement.strip(), ""]

    if results:
        lines += ["## Dependency Outputs", ""]
        for result in results:
            lines += [f"### {result.id} — accepted result of {result.task_id}", ""]
            lines += [result.summary.strip(), ""]
            if result.findings:
                lines += ["Findings:", ""]
                lines += [f"- {finding}" for finding in result.findings]
                lines.append("")
            if result.unresolved_questions:
                lines += ["Unresolved questions:", ""]
                lines += [f"- {question}" for question in result.unresolved_questions]
                lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def compile_context(
    snapshot: Snapshot, task_id: str, compiled_at: str | None = None
) -> CompiledContext:
    """Compile the explicit context package for one task (DEC-004, DEC-005)."""
    task = _resolve_task(snapshot, task_id)
    selected, results = _select(snapshot, task)
    body = _render_body(task, selected, results)

    state_refs = tuple(sorted((obj.id, obj.version) for obj in selected.values()))
    dependency_results = tuple((result.task_id, result.id) for result in results)

    # content_hash covers canonical provenance + body, excluding volatile fields
    # (compiled_at, content_hash) per DEC-005 / §9.4
    hash_payload = {
        "task_id": task.id,
        "task_version": task.version,
        "compiler_version": COMPILER_VERSION,
        "state_refs": [{"id": ref, "version": version} for ref, version in state_refs],
        "dependency_results": [
            {"task_id": dep_id, "result_id": result_id}
            for dep_id, result_id in dependency_results
        ],
    }
    canonical = yaml.safe_dump(hash_payload, sort_keys=True, allow_unicode=True) + "\n" + body
    content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    if compiled_at is None:
        compiled_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    frontmatter = dict(hash_payload)
    frontmatter["content_hash"] = content_hash
    frontmatter["compiled_at"] = compiled_at
    document = (
        "---\n"
        + yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True, width=88)
        + "---\n\n"
        + body
    )

    return CompiledContext(
        task_id=task.id,
        task_version=task.version,
        compiler_version=COMPILER_VERSION,
        state_refs=state_refs,
        dependency_results=dependency_results,
        content_hash=content_hash,
        compiled_at=compiled_at,
        body=body,
        document=document,
    )


def write_context(smcc_dir: Path | str, context: CompiledContext) -> Path:
    """Write a compiled context to its content-addressed path.

    Contexts are content-addressed by content_hash, so an existing file with
    the same name already holds identical deterministic content; rewriting it
    is a no-op by construction and the existing path is returned.
    """
    path = Path(smcc_dir) / "contexts" / context.task_id / f"{context.content_hash}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="") as handle:
            handle.write(context.document)
    except FileExistsError:
        pass
    return path


# ---- staleness (DEC-005, ARCHITECTURE §12.1) ----


@dataclass(frozen=True)
class StaleInput:
    """One recorded input that no longer matches authoritative state."""

    # task: the task's own version drifted; state: a state_refs entry drifted;
    # dependency: a dependency's accepted_result no longer names the recorded Result
    kind: str  # "task" | "state" | "dependency"
    id: str
    recorded: str
    current: str

    def render(self) -> str:
        return f"{self.id}: recorded {self.recorded}, current {self.current}"


@dataclass(frozen=True)
class StalenessReport:
    """Staleness of one compiled context against the current snapshot."""

    task_id: str
    content_hash: str
    stale_inputs: tuple[StaleInput, ...]
    path: Path | None = None

    @property
    def fresh(self) -> bool:
        return not self.stale_inputs


def _parse_frontmatter(document: str, path: Path | None) -> dict:
    """Parse and structurally validate provenance frontmatter (DEC-004 shape)."""
    where = path or "<document>"
    parts = document.split("---\n", 2)
    if len(parts) != 3 or parts[0].strip():
        raise CompileError(f"{where}: missing provenance frontmatter")
    try:
        frontmatter = yaml.safe_load(parts[1])
    except yaml.YAMLError as exc:
        raise CompileError(f"{where}: invalid frontmatter YAML: {exc}") from exc
    if not isinstance(frontmatter, dict):
        raise CompileError(f"{where}: frontmatter is not a mapping")

    for field_name, field_type in (
        ("task_id", str),
        ("task_version", int),
        ("content_hash", str),
        ("state_refs", list),
        ("dependency_results", list),
    ):
        if not isinstance(frontmatter.get(field_name), field_type):
            raise CompileError(
                f"{where}: frontmatter field '{field_name}' missing or not {field_type.__name__}"
            )
    for ref in frontmatter["state_refs"]:
        if not (isinstance(ref, dict) and isinstance(ref.get("id"), str) and isinstance(ref.get("version"), int)):
            raise CompileError(f"{where}: state_refs entries must be mappings with id and version")
    for dep_ref in frontmatter["dependency_results"]:
        if not (
            isinstance(dep_ref, dict)
            and isinstance(dep_ref.get("task_id"), str)
            and isinstance(dep_ref.get("result_id"), str)
        ):
            raise CompileError(
                f"{where}: dependency_results entries must be mappings with task_id and result_id"
            )
    return frontmatter


def check_context(snapshot: Snapshot, document: str, path: Path | None = None) -> StalenessReport:
    """Check one compiled context document's recorded inputs against the snapshot.

    A context is stale when any recorded input version or accepted dependency
    result no longer matches the currently authoritative input (DEC-005); every
    changed input is reported individually so the cause is identifiable.
    """
    frontmatter = _parse_frontmatter(document, path)
    task_id = frontmatter["task_id"]
    task_version = frontmatter["task_version"]

    objects = snapshot.by_id()
    stale: list[StaleInput] = []

    task = objects.get(task_id)
    if not isinstance(task, Task):
        stale.append(StaleInput("task", task_id, f"v{task_version}", "missing"))
    elif task.version != task_version:
        stale.append(StaleInput("task", task_id, f"v{task_version}", f"v{task.version}"))

    for ref in frontmatter["state_refs"]:
        obj = objects.get(ref["id"])
        if obj is None or not isinstance(obj, StateObject):
            stale.append(StaleInput("state", ref["id"], f"v{ref['version']}", "missing"))
        elif obj.version != ref["version"]:
            stale.append(StaleInput("state", ref["id"], f"v{ref['version']}", f"v{obj.version}"))

    for dep_ref in frontmatter["dependency_results"]:
        dep_task_id = dep_ref["task_id"]
        recorded = dep_ref["result_id"]
        dep = objects.get(dep_task_id)
        result = objects.get(recorded)
        if not isinstance(dep, Task):
            stale.append(StaleInput("dependency", dep_task_id, recorded, "missing"))
        elif dep.accepted_result != recorded:
            stale.append(StaleInput("dependency", dep_task_id, recorded, dep.accepted_result or "none"))
        elif not isinstance(result, Result) or result.task_id != dep_task_id:
            # accepted_result still names the recorded id, but the Result itself is gone
            stale.append(StaleInput("dependency", dep_task_id, recorded, "missing"))

    return StalenessReport(
        task_id=task_id,
        content_hash=frontmatter["content_hash"],
        stale_inputs=tuple(stale),
        path=path,
    )


def check_task_contexts(
    smcc_dir: Path | str, snapshot: Snapshot, task_id: str
) -> list[StalenessReport]:
    """Check every compiled context stored for a task, in stable path order."""
    contexts_dir = Path(smcc_dir) / "contexts" / task_id
    reports: list[StalenessReport] = []
    if contexts_dir.is_dir():
        for context_path in sorted(contexts_dir.glob("*.md")):
            document = context_path.read_text(encoding="utf-8")
            reports.append(check_context(snapshot, document, path=context_path))
    return reports
