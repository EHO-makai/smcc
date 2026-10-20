# Development Notes

Concise, durable notes for working in this repo. See [AGENTS.md](../AGENTS.md)
for agent instructions.

## Python tooling

- Run all Python through `uv`. Never call `.venv\Scripts\python.exe`, bare
  `python`, or `pip` directly.
- Run tests with `uv run pytest -q`.
- Validate SMCC state with `uv run smcc validate`.
- `uv.lock` is committed. If a `uv` command changes it, commit the update with
  the related change.
