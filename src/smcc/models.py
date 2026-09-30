"""Pydantic schemas for the v1 SMCC object model.

Authoritative state types (DEC-002): Goal, Requirement, Constraint, Decision,
Question, Finding. Task, Result, and Proposal are SMCC objects outside the
authoritative state/ hierarchy but carry the same metadata discipline.
"""

from __future__ import annotations

import re
from datetime import date
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = 1

# type name -> required ID prefix (DEC-010)
ID_PREFIXES: dict[str, str] = {
    "Goal": "GOAL",
    "Requirement": "REQ",
    "Constraint": "CON",
    "Decision": "DEC",
    "Question": "QUESTION",
    "Finding": "FINDING",
    "Task": "TASK",
    "Result": "RESULT",
    "Proposal": "PROP",
}


class StateStatus(str, Enum):
    draft = "draft"
    accepted = "accepted"
    retired = "retired"


class TaskStatus(str, Enum):
    proposed = "proposed"
    ready = "ready"
    in_progress = "in_progress"
    blocked = "blocked"
    review = "review"
    accepted = "accepted"
    rejected = "rejected"
    superseded = "superseded"


class ProposalStatus(str, Enum):
    proposed = "proposed"
    accepted = "accepted"
    rejected = "rejected"


class ProposalOperation(str, Enum):
    create = "create"
    update = "update"
    supersede = "supersede"


class SMCCObject(BaseModel):
    """Common metadata carried by every persisted SMCC object."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: str
    schema_version: int = Field(ge=1)
    version: int = Field(ge=1)
    created_at: date
    updated_at: date
    source: str
    supersedes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _id_matches_type(self) -> "SMCCObject":
        prefix = ID_PREFIXES.get(self.type)
        if prefix is None:
            raise ValueError(f"unknown SMCC object type {self.type!r}")
        if not re.fullmatch(rf"{prefix}-\d{{3,}}", self.id):
            raise ValueError(
                f"id {self.id!r} does not match required pattern {prefix}-NNN for type {self.type!r}"
            )
        return self


class StateObject(SMCCObject):
    """An authoritative state object under .smcc/state/."""

    status: StateStatus
    title: str
    statement: str


class Goal(StateObject):
    type: Literal["Goal"] = "Goal"


class Requirement(StateObject):
    type: Literal["Requirement"] = "Requirement"


class Constraint(StateObject):
    type: Literal["Constraint"] = "Constraint"
    # Constraints declare their own scope; project-scoped constraints are
    # always included by the context compiler (ARCHITECTURE.md §9.1).
    scope: Literal["project"]


class Decision(StateObject):
    type: Literal["Decision"] = "Decision"


class Question(StateObject):
    type: Literal["Question"] = "Question"


class Finding(StateObject):
    type: Literal["Finding"] = "Finding"


class Task(SMCCObject):
    type: Literal["Task"] = "Task"
    status: TaskStatus
    title: str
    goal: str
    task_dependencies: list[str] = Field(default_factory=list)
    context_refs: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    assigned_agent: str | None = None
    outputs: list[str] = Field(default_factory=list)
    accepted_result: str | None = None
    review_state: str | None = None

    @model_validator(mode="after")
    def _accepted_result_invariant(self) -> "Task":
        if self.status == TaskStatus.accepted and self.accepted_result is None:
            raise ValueError("accepted_result must be set when status is 'accepted'")
        if self.status != TaskStatus.accepted and self.accepted_result is not None:
            raise ValueError(
                f"accepted_result must be null unless status is 'accepted' (status is {self.status.value!r})"
            )
        return self


class GitProvenance(BaseModel):
    """Level 1 Git provenance (DEC-011): recorded, never transactional."""

    model_config = ConfigDict(extra="forbid")

    base_commit: str | None = None
    resulting_commit: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    diff_reference: str | None = None


class Result(BaseModel):
    """A structured agent result (DEC-007). Results are immutable: a retry or
    correction produces a new Result id, so version stays 1."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal["Result"] = "Result"
    schema_version: int = Field(ge=1)
    version: Literal[1] = 1
    task_id: str
    created_at: date
    source: str
    summary: str
    work_performed: list[str] = Field(default_factory=list)
    files_changed: list[str] = Field(default_factory=list)
    tests_run: list[str] = Field(default_factory=list)
    test_results: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    proposals: list[str] = Field(default_factory=list)
    follow_up_tasks: list[str] = Field(default_factory=list)
    # Provenance of the context the agent actually saw. Before the compiler
    # exists, bootstrap results use context_source: manual with no hash.
    context_source: Literal["compiled", "manual"]
    context_content_hash: str | None = None
    git: GitProvenance | None = None

    @model_validator(mode="after")
    def _validate(self) -> "Result":
        if not re.fullmatch(r"RESULT-\d{3,}", self.id):
            raise ValueError(f"id {self.id!r} does not match required pattern RESULT-NNN")
        if not re.fullmatch(r"TASK-\d{3,}", self.task_id):
            raise ValueError(f"task_id {self.task_id!r} does not match required pattern TASK-NNN")
        if self.context_source == "compiled" and self.context_content_hash is None:
            raise ValueError("context_content_hash is required when context_source is 'compiled'")
        return self


class Proposal(SMCCObject):
    """One proposed change to one authoritative state object (DEC-008)."""

    type: Literal["Proposal"] = "Proposal"
    status: ProposalStatus
    operation: ProposalOperation
    target_id: str
    # Optimistic concurrency check: required for update/supersede (DEC-008).
    expected_version: int | None = None
    payload: dict = Field(default_factory=dict)
    result_id: str | None = None
    rationale: str | None = None

    @model_validator(mode="after")
    def _operation_invariants(self) -> "Proposal":
        if self.operation in (ProposalOperation.update, ProposalOperation.supersede):
            if self.expected_version is None:
                raise ValueError(
                    f"expected_version is required for operation {self.operation.value!r}"
                )
        return self


class ProjectConfig(BaseModel):
    """.smcc/project.yaml - sidecar configuration, not an authoritative object."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1)
    name: str
    description: str
    goal_refs: list[str] = Field(default_factory=list)
    created_at: date


AnyStateObject = Annotated[
    Union[Goal, Requirement, Constraint, Decision, Question, Finding],
    Field(discriminator="type"),
]

AnySMCCObject = Annotated[
    Union[Goal, Requirement, Constraint, Decision, Question, Finding, Task, Result, Proposal],
    Field(discriminator="type"),
]
