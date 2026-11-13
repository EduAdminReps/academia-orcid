# academia-orcid task runner. Run `just` (no args) to list recipes.
#
# Recipes go through `uv run`, which always targets this project's own .venv
# (and installs the dev group: pytest, ruff, mypy).
# This repo owns filling ORCID_JSON/; other repos call `just prefetch` here
# (tamu-coe-faculty-profiles: `just prefetch`, academia-openalex: `just prefetch`).

python := "uv run python"
db := env("COE_DATA_DB", justfile_directory() / "../coe-data-db/en.db")

# List available recipes.
default:
    @just --list

# Fill ORCID_JSON/ (missing, stale or partial records only).
# Scope with --dept CODE / --uin UIN / --uin-file PATH; --force refetches; --dry-run lists.
prefetch *args:
    {{ python }} run_prefetch.py --mapping-db {{ db }} {{ args }}

# Run the test suite (extra arguments go to pytest, e.g. `just test -k extract`).
test *args:
    uv run pytest {{ args }}

# Lint with ruff and check the formatting (`just format` applies it).
lint:
    uv run ruff check .
    uv run ruff format --check .

# Type-check the package and entry points (settings in pyproject.toml).
typecheck:
    uv run mypy

# Format with ruff.
format:
    uv run ruff format .

# Lint, type-check, then test.
check: lint typecheck test
