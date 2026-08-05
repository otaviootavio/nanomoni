---
name: using-poetry
description: How to use Poetry for dependency management, virtual environment, and running commands in NanoMoni. Use when adding or removing dependencies, running scripts in the venv, resolving lock/sync issues, or when the user asks about Poetry, pyproject.toml, or the project venv.
---

# Using Poetry

## Setup and run

- **Python**: Project requires **Python 3.9** (bounded `<3.10.0` in `pyproject.toml`). Use pyenv: `pyenv install 3.9` then `pyenv local 3.9` in the repo.
- **Install**: `poetry install` — creates the venv (if needed) and installs all dependencies from lock file.
- **Run a command in the venv**: `poetry run <command>`, e.g. `poetry run pytest tests/unit`, `poetry run mypy src`.
- **Venv path**: `poetry env info --path` — use this path when configuring the Python interpreter in the editor.
- **Activate shell**: `poetry shell` — spawns a shell with the venv activated (optional; `poetry run` is usually enough).

All commands assume you are in the repo root.

---

## Project layout

- **Package**: Code lives under `src/nanomoni`. In `pyproject.toml`, `[tool.poetry]` declares `packages = [{include = "nanomoni", from = "src"}]`.
- **Dependencies**: Declared in `[project].dependencies` (PEP 621). Lock file is `poetry.lock`; do not edit it by hand.

---

## Adding a dependency

1. **Edit `pyproject.toml`**: Add the package under `[project].dependencies` with a version constraint, e.g. `"some-pkg (>=1.0.0,<2.0.0)"`.
2. **Update lock and install**:
   ```sh
   poetry lock
   poetry install
   ```
   Use `poetry add some-pkg` only if you prefer Poetry to edit `pyproject.toml` and lock for you; the project uses PEP 621, so manual edit + `poetry lock` + `poetry install` is consistent.

For **dev-only** dependencies, add them to a dev group or keep them in `[project].dependencies` if the project does not use optional groups.

---

## Removing a dependency

Use `poetry remove` (updates `pyproject.toml` and lock, then syncs the venv):

```sh
poetry remove <package-name>
```

Example: `poetry remove requests`. Use `--dry-run` to preview. For groups: `--group dev` (or the group name).

**Alternative**: Remove the line from `[project].dependencies` in `pyproject.toml`, then run `poetry lock` and `poetry install`.

---

## Common commands

| Goal | Command |
|------|--------|
| Install deps | `poetry install` |
| Run command in venv | `poetry run <cmd>` |
| Update lock after editing deps | `poetry lock` then `poetry install` |
| Show venv path | `poetry env info --path` |
| List installed packages | `poetry show` |
| Add dependency (optional) | `poetry add <pkg>` (may conflict with PEP 621 layout) |
| Remove dependency | `poetry remove <pkg>` |

---

## Troubleshooting

- **Wrong Python**: Ensure Python 3.9 is active (`python --version`). Use `pyenv local 3.9` in the repo.
- **Stale lock**: After editing `pyproject.toml`, always run `poetry lock` then `poetry install`.
- **Broken env**: `poetry env remove python` (or the path from `poetry env info --path`), then `poetry install` to recreate.

For running tests and lint, see the **nanomoni-dev-workflow** skill.
