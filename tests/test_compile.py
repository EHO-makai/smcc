"""Context compiler: determinism, provenance, explicit selection (TASK-003)."""

import shutil
from pathlib import Path

import pytest
import yaml

from smcc import Store
from smcc.cli import EXIT_INVALID, EXIT_VALID, main
from smcc.compile import (
    COMPILER_VERSION,
    CompileError,
    check_task_contexts,
    compile_context,
    write_context,
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


def _compile(smcc_dir: Path, task_id: str = "TASK-003", compiled_at: str | None = None):
    return compile_context(Store(smcc_dir).load_all(), task_id, compiled_at=compiled_at)


def _frontmatter(document: str) -> dict:
    _, fm_text, _ = document.split("---\n", 2)
    return yaml.safe_load(fm_text)


class TestDeterminism:
    def test_recompiling_unchanged_inputs_yields_identical_hash(self, fixture_copy: Path):
        first = _compile(fixture_copy, compiled_at="2026-01-01T00:00:00+00:00")
        second = _compile(fixture_copy, compiled_at="2026-02-02T00:00:00+00:00")
        assert first.content_hash == second.content_hash
        assert first.body == second.body  # stable ordering across runs
        assert first.compiled_at != second.compiled_at  # volatile field excluded from hash

    def test_changed_input_version_changes_hash_and_is_identifiable(self, fixture_copy: Path):
        before = _compile(fixture_copy)
        _edit(fixture_copy / "state" / "decisions" / "DEC-004.yaml", version=2)
        after = _compile(fixture_copy)

        assert before.content_hash != after.content_hash
        changed = set(after.state_refs) - set(before.state_refs)
        assert changed == {("DEC-004", 2)}  # the changed input is identifiable


class TestProvenanceFrontmatter:
    def test_frontmatter_records_all_consumed_objects(self, fixture_copy: Path):
        context = _compile(fixture_copy)
        fm = _frontmatter(context.document)

        assert fm["task_id"] == "TASK-003"
        assert fm["task_version"] == context.task_version
        assert fm["compiler_version"] == COMPILER_VERSION
        assert fm["content_hash"] == context.content_hash
        assert fm["compiled_at"] == context.compiled_at
        assert {"task_id": "TASK-001", "result_id": "RESULT-001"} in fm["dependency_results"]

        # every object rendered in the body is recorded as (id, version), and
        # everything recorded is rendered: provenance matches consumption exactly
        rendered = {
            (line.split()[1], int(line.split()[2].strip("()v")))
            for line in context.body.splitlines()
            if line.startswith("### ") and not line.startswith("### RESULT-")
        }
        recorded = {(ref["id"], ref["version"]) for ref in fm["state_refs"]}
        assert rendered == recorded

    def test_state_refs_are_stably_ordered(self, fixture_copy: Path):
        fm = _frontmatter(_compile(fixture_copy).document)
        ids = [ref["id"] for ref in fm["state_refs"]]
        assert ids == sorted(ids)


class TestSelection:
    def test_body_contains_exactly_the_explicit_selection_set(self, fixture_copy: Path):
        context = _compile(fixture_copy)
        body = context.body

        # CON-003: project goal, project-scoped constraints, context_refs, dep result
        assert "### GOAL-001" in body
        assert "### CON-003" in body
        for ref in ("DEC-003", "DEC-004", "DEC-005", "DEC-006"):
            assert f"### {ref}" in body
        assert "### RESULT-001 — accepted result of TASK-001" in body

        # not referenced by TASK-003: excluded despite existing in state
        # (heading-level check: ids may appear inside included objects' prose)
        assert "### DEC-001" not in body
        assert "### QUESTION-001" not in body

    def test_empty_headings_are_omitted(self, fixture_copy: Path):
        body = _compile(fixture_copy).body
        assert "## Relevant Requirements" not in body  # no Requirement selected
        assert "## Relevant Artifacts" not in body  # deferred in v1
        assert "## Execution Instructions" not in body

    def test_retired_project_constraint_is_excluded(self, fixture_copy: Path):
        _edit(fixture_copy / "state" / "constraints" / "CON-001.yaml", status="retired", version=3)
        body = _compile(fixture_copy).body
        assert "CON-001" not in body

    def test_duplicate_refs_are_deduped(self, fixture_copy: Path):
        # name the project goal and a project constraint explicitly as well
        _edit(
            fixture_copy / "tasks" / "TASK-003" / "task.yaml",
            context_refs=["GOAL-001", "CON-003", "DEC-004"],
        )
        body = _compile(fixture_copy).body
        assert body.count("### GOAL-001") == 1
        assert body.count("### CON-003") == 1


class TestCompileErrors:
    def test_unknown_task(self, fixture_copy: Path):
        with pytest.raises(CompileError, match="task not found"):
            _compile(fixture_copy, task_id="TASK-999")

    def test_dangling_context_ref(self, fixture_copy: Path):
        _edit(fixture_copy / "tasks" / "TASK-003" / "task.yaml", context_refs=["DEC-999"])
        with pytest.raises(CompileError, match="unknown object 'DEC-999'"):
            _compile(fixture_copy)

    def test_context_ref_to_non_state_object(self, fixture_copy: Path):
        _edit(fixture_copy / "tasks" / "TASK-003" / "task.yaml", context_refs=["TASK-001"])
        with pytest.raises(CompileError, match="not an authoritative state object"):
            _compile(fixture_copy)

    def test_dependency_without_accepted_result(self, fixture_copy: Path):
        # seed a non-accepted TASK-003 so a task depending on it cannot compile
        _edit(
            fixture_copy / "tasks" / "TASK-003" / "task.yaml",
            status="in_progress",
            accepted_result=None,
        )
        task_dir = fixture_copy / "tasks" / "TASK-900"
        task_dir.mkdir()
        template = yaml.safe_load(
            (fixture_copy / "tasks" / "TASK-003" / "task.yaml").read_text(encoding="utf-8")
        )
        template.update(
            id="TASK-900",
            version=1,
            status="in_progress",
            accepted_result=None,
            task_dependencies=["TASK-003"],
            outputs=[],
        )
        (task_dir / "task.yaml").write_text(
            yaml.safe_dump(template, sort_keys=False), encoding="utf-8"
        )
        with pytest.raises(CompileError, match="TASK-003 has no accepted result"):
            _compile(fixture_copy, task_id="TASK-900")


class TestWriteContext:
    def test_content_addressed_path_and_round_trip(self, fixture_copy: Path):
        context = _compile(fixture_copy)
        path = write_context(fixture_copy, context)

        assert path == fixture_copy / "contexts" / "TASK-003" / f"{context.content_hash}.md"
        assert path.read_text(encoding="utf-8") == context.document
        # idempotent: rewriting the same content-addressed context is a no-op
        assert write_context(fixture_copy, context) == path


class TestCLI:
    def test_compile_succeeds(self, fixture_copy: Path, capsys):
        assert main(["compile", "TASK-003", "--smcc-dir", str(fixture_copy)]) == EXIT_VALID
        out = capsys.readouterr().out
        path_line, hash_line = out.strip().splitlines()
        content_hash = hash_line.removeprefix("content_hash: ")
        # assert the specific file; the live fixture may already carry committed contexts
        assert (fixture_copy / "contexts" / "TASK-003" / f"{content_hash}.md").is_file()
        assert path_line.endswith(f"{content_hash}.md")

    def test_compile_unknown_task_fails(self, fixture_copy: Path, capsys):
        assert main(["compile", "TASK-999", "--smcc-dir", str(fixture_copy)]) == EXIT_INVALID
        assert "task not found" in capsys.readouterr().err


def _check(smcc_dir: Path, task_id: str = "TASK-004"):
    return check_task_contexts(smcc_dir, Store(smcc_dir).load_all(), task_id)


class TestStaleness:
    def test_fresh_against_unchanged_inputs(self, fixture_copy: Path):
        context = _compile(fixture_copy, task_id="TASK-004")
        write_context(fixture_copy, context)
        report = next(r for r in _check(fixture_copy) if r.content_hash == context.content_hash)
        assert report.fresh
        assert report.stale_inputs == ()

    def test_bumped_state_version_is_identified(self, fixture_copy: Path):
        context = _compile(fixture_copy, task_id="TASK-004")
        write_context(fixture_copy, context)
        _edit(fixture_copy / "state" / "decisions" / "DEC-005.yaml", version=2)

        report = next(r for r in _check(fixture_copy) if r.content_hash == context.content_hash)
        assert not report.fresh
        assert ("state", "DEC-005", "v1", "v2") in [
            (s.kind, s.id, s.recorded, s.current) for s in report.stale_inputs
        ]

    def test_changed_dependency_result_is_identified(self, fixture_copy: Path):
        context = _compile(fixture_copy, task_id="TASK-004")
        write_context(fixture_copy, context)
        # dependency re-accepted with a different result than the one recorded
        _edit(
            fixture_copy / "tasks" / "TASK-003" / "task.yaml",
            version=8,
            accepted_result="RESULT-005",
        )

        report = next(r for r in _check(fixture_copy) if r.content_hash == context.content_hash)
        stale = {(s.kind, s.id): (s.recorded, s.current) for s in report.stale_inputs}
        assert stale[("dependency", "TASK-003")] == ("RESULT-003", "RESULT-005")
        # the task version drift of TASK-003 is a dependency concern, not TASK-004's own
        assert ("task", "TASK-004") not in stale

    def test_missing_input_is_identified(self, fixture_copy: Path):
        context = _compile(fixture_copy, task_id="TASK-004")
        write_context(fixture_copy, context)
        (fixture_copy / "state" / "decisions" / "DEC-004.yaml").unlink()

        report = next(r for r in _check(fixture_copy) if r.content_hash == context.content_hash)
        assert ("state", "DEC-004", "v1", "missing") in [
            (s.kind, s.id, s.recorded, s.current) for s in report.stale_inputs
        ]

    def test_own_task_version_drift_is_identified(self, fixture_copy: Path):
        context = _compile(fixture_copy, task_id="TASK-004")
        write_context(fixture_copy, context)
        # seed a version guaranteed to differ from whatever the living fixture holds
        _edit(fixture_copy / "tasks" / "TASK-004" / "task.yaml", version=context.task_version + 1)

        report = next(r for r in _check(fixture_copy) if r.content_hash == context.content_hash)
        assert ("task", "TASK-004") in {(s.kind, s.id) for s in report.stale_inputs}

    def test_live_task_003_context_is_stale_from_con_003_amendment(self, smcc_dir: Path):
        # real dogfood case: the committed TASK-003 context recorded CON-003 v2,
        # amended to v3 during PR #3 review; task version also moved v5 -> v7
        reports = check_task_contexts(smcc_dir, Store(smcc_dir).load_all(), "TASK-003")
        assert reports
        stale_ids = {s.id for r in reports for s in r.stale_inputs}
        assert "CON-003" in stale_ids


class TestStaleCLI:
    def test_fresh_context_exits_zero(self, fixture_copy: Path, capsys):
        write_context(fixture_copy, _compile(fixture_copy, task_id="TASK-004"))
        assert main(["stale", "TASK-004", "--smcc-dir", str(fixture_copy)]) == EXIT_VALID
        assert ": fresh" in capsys.readouterr().out

    def test_all_stale_exits_one_and_names_inputs(self, fixture_copy: Path, capsys):
        write_context(fixture_copy, _compile(fixture_copy, task_id="TASK-004"))
        _edit(fixture_copy / "state" / "decisions" / "DEC-005.yaml", version=2)
        assert main(["stale", "TASK-004", "--smcc-dir", str(fixture_copy)]) == EXIT_INVALID
        out = capsys.readouterr().out
        assert ": stale" in out
        assert "DEC-005: recorded v1, current v2" in out

    def test_no_compiled_contexts_exits_one(self, fixture_copy: Path, capsys):
        assert main(["stale", "TASK-001", "--smcc-dir", str(fixture_copy)]) == EXIT_INVALID
        assert "no compiled contexts" in capsys.readouterr().err
