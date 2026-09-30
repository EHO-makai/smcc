"""Schema invariants for the v1 SMCC object model."""

from datetime import date

import pytest
from pydantic import ValidationError

from smcc import (
    Constraint,
    Decision,
    Proposal,
    Result,
    Task,
)


def _common(id: str, type_: str) -> dict:
    return {
        "id": id,
        "type": type_,
        "schema_version": 1,
        "version": 1,
        "created_at": date(2026, 9, 30),
        "updated_at": date(2026, 9, 30),
        "source": "test",
    }


def _state(id: str, type_: str) -> dict:
    return _common(id, type_) | {"status": "accepted", "title": "t", "statement": "s"}


def _task(**overrides) -> dict:
    data = _common("TASK-001", "Task") | {
        "status": "ready",
        "title": "t",
        "goal": "g",
    }
    data.update(overrides)
    return data


class TestIdPrefix:
    def test_valid_decision(self):
        assert Decision.model_validate(_state("DEC-001", "Decision")).id == "DEC-001"

    def test_wrong_prefix_rejected(self):
        with pytest.raises(ValidationError, match="does not match required pattern"):
            Decision.model_validate(_state("GOAL-001", "Decision"))

    def test_malformed_id_rejected(self):
        with pytest.raises(ValidationError, match="does not match required pattern"):
            Decision.model_validate(_state("DEC-1", "Decision"))


class TestConstraintScope:
    def test_project_scope(self):
        con = Constraint.model_validate(_state("CON-001", "Constraint") | {"scope": "project"})
        assert con.scope == "project"

    def test_scope_required(self):
        with pytest.raises(ValidationError):
            Constraint.model_validate(_state("CON-001", "Constraint"))

    def test_unknown_scope_rejected(self):
        with pytest.raises(ValidationError):
            Constraint.model_validate(_state("CON-001", "Constraint") | {"scope": "galactic"})


class TestTaskInvariants:
    def test_accepted_requires_accepted_result(self):
        with pytest.raises(ValidationError, match="accepted_result must be set"):
            Task.model_validate(_task(status="accepted"))

    def test_accepted_with_result_ok(self):
        task = Task.model_validate(_task(status="accepted", accepted_result="RESULT-001"))
        assert task.accepted_result == "RESULT-001"

    def test_non_accepted_with_result_rejected(self):
        with pytest.raises(ValidationError, match="accepted_result must be null"):
            Task.model_validate(_task(status="ready", accepted_result="RESULT-001"))

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            Task.model_validate(_task(status="doing-stuff"))

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            Task.model_validate(_task(shiny_new_field=True))


class TestResultInvariants:
    def _result(self, **overrides) -> dict:
        data = {
            "id": "RESULT-001",
            "type": "Result",
            "schema_version": 1,
            "version": 1,
            "task_id": "TASK-001",
            "created_at": date(2026, 9, 30),
            "source": "test",
            "summary": "s",
            "context_source": "manual",
        }
        data.update(overrides)
        return data

    def test_manual_context_without_hash_ok(self):
        result = Result.model_validate(self._result())
        assert result.context_content_hash is None

    def test_compiled_context_requires_hash(self):
        with pytest.raises(ValidationError, match="context_content_hash is required"):
            Result.model_validate(self._result(context_source="compiled"))

    def test_version_pinned_to_one(self):
        with pytest.raises(ValidationError):
            Result.model_validate(self._result(version=2))


class TestProposalInvariants:
    def _proposal(self, **overrides) -> dict:
        data = _common("PROP-001", "Proposal") | {
            "status": "proposed",
            "operation": "create",
            "target_id": "DEC-099",
        }
        data.update(overrides)
        return data

    def test_create_without_expected_version_ok(self):
        assert Proposal.model_validate(self._proposal()).expected_version is None

    @pytest.mark.parametrize("operation", ["update", "supersede"])
    def test_update_and_supersede_require_expected_version(self, operation):
        with pytest.raises(ValidationError, match="expected_version is required"):
            Proposal.model_validate(self._proposal(operation=operation))

    def test_update_with_expected_version_ok(self):
        prop = Proposal.model_validate(self._proposal(operation="update", expected_version=3))
        assert prop.expected_version == 3
