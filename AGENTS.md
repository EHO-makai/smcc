# Agent Instructions

## Legacy repository memory

Accumulated project knowledge from the retired Copilot memory tool is kept in
[docs/legacy-memory/](docs/legacy-memory/INDEX.md).

- When you start work, read [docs/legacy-memory/INDEX.md](docs/legacy-memory/INDEX.md).
- Before making substantive changes, read the legacy memory files that relate to the task.
- Treat legacy memory as historical context. It may not reflect current project state.
- This repo is SMCC-managed. If accepted SMCC state in `.smcc/` conflicts with legacy memory, prefer the SMCC state.
- Before substantive development work, consult docs/development-notes.md, if it exists, and any other repository documentation relevant to the task.
- Report contradictions (between memory files, or between memory and the code or SMCC state) to the user. Don't resolve them silently.
- Do not modify or add to docs/legacy-memory/. Its files are preserved historical records.

## New memory information

- When you discover durable, repository-specific knowledge that would benefit future development sessions, propose recording it in the appropriate repository documentation. If no suitable document exists, use docs/development-notes.md.

- This includes useful testing conventions, operational procedures, debugging lessons, and implementation pitfalls.

- Keep these notes concise and actionable. Do not duplicate information already maintained elsewhere.

- Use SMCC for knowledge that naturally belongs in authoritative structured project state.

- At the end of substantive development work, consider whether any newly discovered knowledge is worth preserving. Do not create notes merely to document routine activity.
