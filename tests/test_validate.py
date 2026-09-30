"""smcc validate: the fixture passes, and every seeded defect is detected (TASK-002)."""

import shutil
from pathlib import Path

import pytest
import yaml

from smcc.cli import EXIT_INVALID, EXIT_USAGE, EXIT_VALID, main
from smcc.validate import (
    ACCEPTED_RESULT,
    DANGLING_REF,
    DEPENDENCY_CYCLE,
    DUPLICATE_ID,
    LOCATION,
    PROVENANCE,
    SCHEMA,
    STATUS_DEPENDENCY,
    validate,
)


@pytest.fixture()
def fixture_copy(smcc_dir: Path, tmp_path: Path) -> Path:
    copy = tmp_path / ".smcc"
    shutil.copytree(smcc_dir, copy)
    return copy


def _edit(path: Path, **updates) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.update(updates)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _codes(smcc_dir: Path) -> set[str]:
    return {issue.code for issue in validate(smcc_dir).issues}


class TestFixtureIsValid:
    def test_bootstrap_fixture_passes(self, smcc_dir: Path):
        report = validate(smcc_dir)
        assert report.ok, [issue.render() for issue in report.issues]


class TestSeededDefects:
    def test_duplicate_id(self, fixture_copy: Path):
        src = fixture_copy / "state" / "decisions" / "DEC-001.yaml"
        shutil.copy(src, src.with_name("DEC-001-copy.yaml"))
        assert DUPLICATE_ID in _codes(fixture_copy)

    def test_dangling_context_ref(self, fixture_copy: Path):
        task = fixture_copy / "tasks" / "TASK-003" / "task.yaml"
        _edit(task, context_refs=["DEC-999"])
        assert DANGLING_REF in _codes(fixture_copy)

    def test_dangling_task_dependency(self, fixture_copy: Path):
        task = fixture_copy / "tasks" / "TASK-003" / "task.yaml"
        _edit(task, task_dependencies=["TASK-999"])
        assert DANGLING_REF in _codes(fixture_copy)

    def test_dangling_project_goal_ref(self, fixture_copy: Path):
        _edit(fixture_copy / "project.yaml", goal_refs=["GOAL-999"])
        assert DANGLING_REF in _codes(fixture_copy)

    def test_dependency_cycle(self, fixture_copy: Path):
        _edit(
            fixture_copy / "tasks" / "TASK-002" / "task.yaml",
            task_dependencies=["TASK-003"],
        )
        _edit(
            fixture_copy / "tasks" / "TASK-003" / "task.yaml",
            task_dependencies=["TASK-002"],
        )
        assert DEPENDENCY_CYCLE in _codes(fixture_copy)

    def test_invalid_status(self, fixture_copy: Path):
        _edit(fixture_copy / "tasks" / "TASK-003" / "task.yaml", status="bogus")
        assert SCHEMA in _codes(fixture_copy)

    def test_ready_with_unsatisfied_dependency(self, fixture_copy: Path):
        # seed the non-accepted dependency; don't rely on live fixture statuses
        _edit(
            fixture_copy / "tasks" / "TASK-002" / "task.yaml",
            status="in_progress",
            accepted_result=None,
        )
        _edit(
            fixture_copy / "tasks" / "TASK-003" / "task.yaml",
            task_dependencies=["TASK-001", "TASK-002"],
        )
        assert STATUS_DEPENDENCY in _codes(fixture_copy)

    def test_blocked_with_all_dependencies_accepted(self, fixture_copy: Path):
        _edit(fixture_copy / "tasks" / "TASK-003" / "task.yaml", status="blocked")
        assert STATUS_DEPENDENCY in _codes(fixture_copy)

    def test_accepted_result_unresolvable(self, fixture_copy: Path):
        _edit(
            fixture_copy / "tasks" / "TASK-001" / "task.yaml",
            accepted_result="RESULT-999",
        )
        assert ACCEPTED_RESULT in _codes(fixture_copy)

    def test_result_under_wrong_task_directory(self, fixture_copy: Path):
        src = fixture_copy / "tasks" / "TASK-001" / "results" / "RESULT-001.yaml"
        dest_dir = fixture_copy / "tasks" / "TASK-002" / "results"
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dest_dir / "RESULT-001.yaml")
        assert PROVENANCE in _codes(fixture_copy)

    def test_wrong_object_kind_for_directory(self, fixture_copy: Path):
        decision = fixture_copy / "state" / "decisions" / "DEC-001.yaml"
        shutil.copy(decision, fixture_copy / "proposals" / "DEC-001.yaml")
        assert LOCATION in _codes(fixture_copy)

    def test_unparseable_yaml(self, fixture_copy: Path):
        (fixture_copy / "state" / "goals" / "broken.yaml").write_text(
            "{: not yaml", encoding="utf-8"
        )
        assert SCHEMA in _codes(fixture_copy)

    def test_missing_sidecar(self, tmp_path: Path):
        report = validate(tmp_path / "nope")
        assert not report.ok
        assert report.issues[0].code == SCHEMA


class TestDefectsAreIndividuallyReported:
    def test_multiple_defects_all_reported(self, fixture_copy: Path):
        src = fixture_copy / "state" / "decisions" / "DEC-001.yaml"
        shutil.copy(src, src.with_name("DEC-001-copy.yaml"))
        _edit(fixture_copy / "tasks" / "TASK-003" / "task.yaml", context_refs=["DEC-999"])
        codes = _codes(fixture_copy)
        assert {DUPLICATE_ID, DANGLING_REF} <= codes


class TestCli:
    def test_valid_exit_code(self, fixture_copy: Path, capsys):
        assert main(["validate", "--smcc-dir", str(fixture_copy)]) == EXIT_VALID
        assert "valid" in capsys.readouterr().out

    def test_invalid_exit_code(self, fixture_copy: Path, capsys):
        _edit(fixture_copy / "tasks" / "TASK-003" / "task.yaml", context_refs=["DEC-999"])
        assert main(["validate", "--smcc-dir", str(fixture_copy)]) == EXIT_INVALID
        out = capsys.readouterr().out
        assert "dangling-ref" in out
        assert "issue(s) found" in out

    def test_discovery_walks_up(self, fixture_copy: Path, monkeypatch, capsys):
        nested = fixture_copy.parent / "src" / "deep"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)
        assert main(["validate"]) == EXIT_VALID

    def test_no_sidecar_found(self, tmp_path: Path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        assert main(["validate"]) == EXIT_USAGE
