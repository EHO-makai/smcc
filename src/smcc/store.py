"""File-backed store for SMCC objects (CON-002).

Only YAML SMCC data files are loaded; non-SMCC files (.gitkeep etc.) are
ignored rather than treated as malformed state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import yaml
from pydantic import TypeAdapter, ValidationError

from smcc.errors import SMCCFileError, SMCCValidationError
from smcc.models import (
    AnySMCCObject,
    Constraint,
    Decision,
    Finding,
    Goal,
    ProjectConfig,
    Proposal,
    Question,
    Requirement,
    Result,
    StateObject,
    Task,
)

_OBJECT_ADAPTER: TypeAdapter = TypeAdapter(AnySMCCObject)

_YAML_SUFFIXES = {".yaml", ".yml"}

# type -> state/ subdirectory for authoritative objects
_STATE_DIRS: dict[type, str] = {
    Goal: "goals",
    Requirement: "requirements",
    Constraint: "constraints",
    Decision: "decisions",
    Question: "questions",
    Finding: "findings",
}


def _load_yaml(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except OSError as exc:
        raise SMCCFileError(path, f"cannot read file: {exc}") from exc
    except yaml.YAMLError as exc:
        raise SMCCFileError(path, f"invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise SMCCFileError(path, f"expected a YAML mapping, got {type(data).__name__}")
    return data


def _dump_yaml(data: dict) -> str:
    return yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=88,
    )


def parse_object(data: dict, path: Path | None = None) -> AnySMCCObject:
    """Parse a raw mapping into a typed SMCC object, reporting the file on failure."""
    try:
        return _OBJECT_ADAPTER.validate_python(data)
    except ValidationError as exc:
        raise SMCCValidationError(path, exc) from exc


@dataclass
class Snapshot:
    """All SMCC objects loaded from one sidecar directory."""

    project: ProjectConfig
    state_objects: list[StateObject] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    results: list[Result] = field(default_factory=list)
    proposals: list[Proposal] = field(default_factory=list)

    def all_objects(self) -> Iterator[AnySMCCObject]:
        yield from self.state_objects
        yield from self.tasks
        yield from self.results
        yield from self.proposals

    def by_id(self) -> dict[str, AnySMCCObject]:
        return {obj.id: obj for obj in self.all_objects()}


class Store:
    """Load and save SMCC objects under a .smcc/ sidecar directory."""

    def __init__(self, smcc_dir: Path | str) -> None:
        self.smcc_dir = Path(smcc_dir)
        if not self.smcc_dir.is_dir():
            raise SMCCFileError(self.smcc_dir, "sidecar directory does not exist")

    # ---- loading ----

    def load_project(self) -> ProjectConfig:
        path = self.smcc_dir / "project.yaml"
        data = _load_yaml(path)
        try:
            return ProjectConfig.model_validate(data)
        except ValidationError as exc:
            raise SMCCValidationError(path, exc) from exc

    def _data_files(self, directory: Path) -> list[Path]:
        if not directory.is_dir():
            return []
        return sorted(
            p for p in directory.rglob("*") if p.is_file() and p.suffix in _YAML_SUFFIXES
        )

    def load_state_objects(self) -> list[StateObject]:
        objects: list[StateObject] = []
        for path in self._data_files(self.smcc_dir / "state"):
            obj = parse_object(_load_yaml(path), path)
            if not isinstance(obj, StateObject):
                raise SMCCFileError(
                    path, f"expected an authoritative state object, got type {obj.type!r}"
                )
            objects.append(obj)
        return objects

    def load_tasks(self) -> list[Task]:
        tasks: list[Task] = []
        tasks_dir = self.smcc_dir / "tasks"
        if tasks_dir.is_dir():
            for task_file in sorted(tasks_dir.glob("*/task.yaml")):
                obj = parse_object(_load_yaml(task_file), task_file)
                if not isinstance(obj, Task):
                    raise SMCCFileError(task_file, f"expected a Task, got type {obj.type!r}")
                tasks.append(obj)
        return tasks

    def load_results(self) -> list[Result]:
        results: list[Result] = []
        tasks_dir = self.smcc_dir / "tasks"
        if tasks_dir.is_dir():
            for path in sorted(tasks_dir.glob("*/results/*")):
                if not (path.is_file() and path.suffix in _YAML_SUFFIXES):
                    continue
                obj = parse_object(_load_yaml(path), path)
                if not isinstance(obj, Result):
                    raise SMCCFileError(path, f"expected a Result, got type {obj.type!r}")
                results.append(obj)
        return results

    def load_proposals(self) -> list[Proposal]:
        proposals: list[Proposal] = []
        for path in self._data_files(self.smcc_dir / "proposals"):
            obj = parse_object(_load_yaml(path), path)
            if not isinstance(obj, Proposal):
                raise SMCCFileError(path, f"expected a Proposal, got type {obj.type!r}")
            proposals.append(obj)
        return proposals

    def load_all(self) -> Snapshot:
        return Snapshot(
            project=self.load_project(),
            state_objects=self.load_state_objects(),
            tasks=self.load_tasks(),
            results=self.load_results(),
            proposals=self.load_proposals(),
        )

    # ---- saving ----

    def path_for(self, obj: AnySMCCObject) -> Path:
        """Canonical sidecar location for an object."""
        if isinstance(obj, StateObject):
            return self.smcc_dir / "state" / _STATE_DIRS[type(obj)] / f"{obj.id}.yaml"
        if isinstance(obj, Task):
            return self.smcc_dir / "tasks" / obj.id / "task.yaml"
        if isinstance(obj, Result):
            return self.smcc_dir / "tasks" / obj.task_id / "results" / f"{obj.id}.yaml"
        if isinstance(obj, Proposal):
            return self.smcc_dir / "proposals" / f"{obj.id}.yaml"
        raise TypeError(f"no canonical path for object of type {type(obj).__name__}")

    def save(self, obj: AnySMCCObject) -> Path:
        """Write an object to its canonical location.

        Results are immutable (DEC-007): saving over an existing Result file
        is refused rather than silently overwriting it.
        """
        path = self.path_for(obj)
        if isinstance(obj, Result) and path.exists():
            raise SMCCFileError(
                path, "Result files are immutable; a retry or correction must use a new Result id"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        data = obj.model_dump(mode="json")
        path.write_text(_dump_yaml(data), encoding="utf-8")
        return path
