# Legacy Copilot Repository Memory (Recovered)

This directory holds the repository memory that the old VS Code GitHub Copilot
Chat `memory` tool kept for this repo (virtual path `/memories/repo/`). The new
Copilot SDK harness doesn't load those files, so they were copied here
unchanged on 2026-10-19 to keep them discoverable.

**This is historical, unstructured knowledge saved for a later migration.**
It is not authoritative project state. This repo is SMCC-managed: where
accepted SMCC state in `.smcc/` conflicts with these files, the SMCC state
wins. Files are byte-identical copies of the originals and must not be edited,
consolidated, or extended. Record new knowledge in normal repository docs or
in SMCC.

## Original source

| Scope | Location (Windows, per-user, not in Git) |
|---|---|
| Repo memory (recovered) | `%APPDATA%\Code\User\workspaceStorage\5e2f485073e0710b54e5af4ba08619f2\GitHub.copilot-chat\memory-tool\memories\repo\` |
| User/global memory (not recovered) | `%APPDATA%\Code\User\globalStorage\github.copilot-chat\memory-tool\memories\` |

The workspaceStorage folder was matched to this repo by its `workspace.json`,
which points to the folder `.../source/repos/smcc`. No other workspaceStorage
entry references this repo. User-scoped memory (`pr-workflow.md`,
`user-preferences.md`) covers EHO's cross-repo preferences and was left out on
purpose.

## Recovered files

| File | Description | Source last modified | SHA-256 |
|---|---|---|---|
| [project-overview.md](project-overview.md) | SMCC project purpose, principles and bootstrap decisions, followed by a dated running log of TASK-001 to TASK-004 (implementation, acceptance, PRs, review fixes), conventions, open questions and "living-fixture" test lessons. | 2026-09-30 | `D6471B2CE518FA6E40EC02490B9A44435CB9019A590275693595125E393682FD` |

`.gitattributes` in this directory turns off line-ending normalization for the
recovered files, so the hash above still holds after commit and checkout (the
repo uses `core.autocrlf=true`; the original is LF-only, no BOM).

## Known duplicates and ambiguities

There are no duplicate copies. The following were kept as-is and not resolved:

- The file is an append-only log, so earlier entries are superseded by later
  ones. For example, "only docs/architecture.md exists" is followed by
  "docs/architecture.md removed", and constraint `scope: global` is later
  changed to `scope: project`.
- "Fable5 (me)" refers to the agent that wrote the memory, not to the reader.
- Task statuses, version numbers, test counts and "Next: TASK-005" reflect
  the time of writing and may not match current `.smcc/` state or the code.
- The recorded test command (`.\.venv\Scripts\python.exe -m pytest -q`)
  predates EHO's `uv`-only rule (`uv run pytest`).
- PR and commit references (PRs 1 to 5, short SHAs) refer to this repository's
  history.
