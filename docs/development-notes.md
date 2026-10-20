# Development Notes

Concise, durable notes for working in this repo. See [AGENTS.md](../AGENTS.md)
for agent instructions.

## Python tooling

- Run tests with `uv run pytest -q`.
- Validate SMCC state with `uv run smcc validate`.
- `uv run` syncs `.venv` to `uv.lock` before running. Activating `.venv`
  does not read `pyproject.toml` or `uv.lock`. For interactive work, run
  `uv sync` first (and again after pulling, switching branches, or changing
  dependencies), then `.venv\Scripts\activate`.
- Don't `pip install` into `.venv`. It causes drift that the next `uv sync`
  undoes.
- `uv.lock` is committed. If a `uv` command changes it, commit the update with
  the related change.
