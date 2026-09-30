"""The store loads, validates, and round-trips the repository's own bootstrap fixture."""

from datetime import date
from pathlib import Path

import pytest
import yaml

from smcc import Constraint, Decision, Goal, Result, SMCCFileError, SMCCValidationError, Store
from smcc.store import parse_object

FIXTURE_DATE = date(2026, 9, 30)


class TestFixtureLoads:
    def test_project_config(self, store: Store):
        project = store.load_project()
        assert project.name == "smcc"
        assert project.goal_refs == ["GOAL-001"]

    def test_state_object_census(self, store: Store):
        objects = store.load_state_objects()
        ids = {obj.id for obj in objects}
        # known bootstrap objects; the fixture may grow but never lose these
        assert "GOAL-001" in ids
        assert {f"CON-{n:03d}" for n in range(1, 6)} <= ids
        assert {f"DEC-{n:03d}" for n in range(1, 13)} <= ids

    def test_tasks_load(self, store: Store):
        tasks = store.load_tasks()
        assert [t.id for t in tasks] == ["TASK-001", "TASK-002", "TASK-003"]
        by_id = {t.id: t for t in tasks}
        assert by_id["TASK-002"].task_dependencies == ["TASK-001"]
        assert by_id["TASK-003"].task_dependencies == ["TASK-001"]

    def test_constraints_are_project_scoped(self, store: Store):
        constraints = [o for o in store.load_state_objects() if isinstance(o, Constraint)]
        assert len(constraints) == 5
        assert all(c.scope == "project" for c in constraints)

    def test_gitkeep_and_non_yaml_ignored(self, store: Store):
        snapshot = store.load_all()
        # directories holding only .gitkeep files yield no objects and no errors
        task_ids = {t.id for t in snapshot.tasks}
        assert all(r.task_id in task_ids for r in snapshot.results)

    def test_no_duplicate_ids(self, store: Store):
        snapshot = store.load_all()
        ids = [obj.id for obj in snapshot.all_objects()]
        assert len(ids) == len(set(ids))


class TestRoundTrip:
    def test_every_object_round_trips(self, store: Store, tmp_path: Path):
        snapshot = store.load_all()
        copy = Store(tmp_path)
        for obj in snapshot.all_objects():
            saved_path = copy.save(obj)
            reloaded = parse_object(
                yaml.safe_load(saved_path.read_text(encoding="utf-8")), saved_path
            )
            assert reloaded == obj, f"{obj.id} changed across a save/load round trip"


class TestErrorReporting:
    def test_validation_error_names_file_and_field(self, tmp_path: Path):
        bad = tmp_path / "state" / "decisions" / "DEC-001.yaml"
        bad.parent.mkdir(parents=True)
        bad.write_text(
            "id: DEC-001\ntype: Decision\nschema_version: 1\nversion: 0\n"
            "status: accepted\ntitle: t\nstatement: s\n"
            "created_at: 2026-09-30\nupdated_at: 2026-09-30\nsource: test\n",
            encoding="utf-8",
        )
        store = Store(tmp_path)
        with pytest.raises(SMCCValidationError) as excinfo:
            store.load_state_objects()
        message = str(excinfo.value)
        assert "DEC-001.yaml" in message
        assert "version" in message

    def test_non_mapping_yaml_reports_file(self, tmp_path: Path):
        bad = tmp_path / "state" / "goals" / "GOAL-001.yaml"
        bad.parent.mkdir(parents=True)
        bad.write_text("- just\n- a\n- list\n", encoding="utf-8")
        store = Store(tmp_path)
        with pytest.raises(SMCCFileError, match="expected a YAML mapping"):
            store.load_state_objects()

    def test_missing_sidecar_dir(self, tmp_path: Path):
        with pytest.raises(SMCCFileError, match="does not exist"):
            Store(tmp_path / "nope")


class TestResultImmutability:
    def _result(self) -> Result:
        return Result(
            id="RESULT-001",
            schema_version=1,
            task_id="TASK-001",
            created_at=FIXTURE_DATE,
            source="test",
            summary="s",
            context_source="manual",
        )

    def test_save_refuses_overwrite(self, tmp_path: Path):
        store = Store(tmp_path)
        result = self._result()
        store.save(result)
        with pytest.raises(SMCCFileError, match="immutable"):
            store.save(result)

    def test_save_goal_overwrite_allowed(self, tmp_path: Path):
        # in-place versioning (DEC-001): state objects may be rewritten
        store = Store(tmp_path)
        goal = Goal(
            id="GOAL-001",
            schema_version=1,
            version=1,
            status="accepted",
            title="t",
            statement="s",
            created_at=FIXTURE_DATE,
            updated_at=FIXTURE_DATE,
            source="test",
        )
        store.save(goal)
        updated = goal.model_copy(update={"version": 2})
        path = store.save(updated)
        reloaded = parse_object(yaml.safe_load(path.read_text(encoding="utf-8")), path)
        assert isinstance(reloaded, Goal)
        assert reloaded.version == 2
