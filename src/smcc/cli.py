"""smcc command-line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from smcc.compile import compile_context, write_context
from smcc.errors import SMCCError
from smcc.store import Store
from smcc.validate import validate

EXIT_VALID = 0
EXIT_INVALID = 1
EXIT_USAGE = 2


def _discover_smcc_dir(start: Path) -> Path | None:
    for directory in (start, *start.parents):
        candidate = directory / ".smcc"
        if candidate.is_dir():
            return candidate
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="smcc")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser(
        "validate", help="validate the .smcc sidecar (DEC-012 snapshot invariants)"
    )
    validate_parser.add_argument(
        "--smcc-dir",
        type=Path,
        default=None,
        help="sidecar directory (default: nearest .smcc walking up from cwd)",
    )

    compile_parser = subparsers.add_parser(
        "compile", help="compile a task's context package (CON-003 selection set)"
    )
    compile_parser.add_argument("task_id", help="task to compile, e.g. TASK-003")
    compile_parser.add_argument(
        "--smcc-dir",
        type=Path,
        default=None,
        help="sidecar directory (default: nearest .smcc walking up from cwd)",
    )

    args = parser.parse_args(argv)
    if args.command == "validate":
        return _cmd_validate(args.smcc_dir)
    if args.command == "compile":
        return _cmd_compile(args.smcc_dir, args.task_id)
    return EXIT_USAGE  # pragma: no cover - argparse enforces the subcommand


def _cmd_validate(smcc_dir: Path | None) -> int:
    if smcc_dir is None:
        smcc_dir = _discover_smcc_dir(Path.cwd())
        if smcc_dir is None:
            print("error: no .smcc directory found from cwd upward", file=sys.stderr)
            return EXIT_USAGE

    report = validate(smcc_dir)
    for issue in report.issues:
        print(issue.render())
    if report.ok:
        print(f"{smcc_dir}: valid")
        return EXIT_VALID
    print(f"{smcc_dir}: {len(report.issues)} issue(s) found")
    return EXIT_INVALID


def _cmd_compile(smcc_dir: Path | None, task_id: str) -> int:
    if smcc_dir is None:
        smcc_dir = _discover_smcc_dir(Path.cwd())
        if smcc_dir is None:
            print("error: no .smcc directory found from cwd upward", file=sys.stderr)
            return EXIT_USAGE

    try:
        snapshot = Store(smcc_dir).load_all()
        context = compile_context(snapshot, task_id)
        path = write_context(smcc_dir, context)
    except SMCCError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INVALID
    print(path)
    print(f"content_hash: {context.content_hash}")
    return EXIT_VALID


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
