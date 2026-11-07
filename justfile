# academia-orcid task runner. Run `just` (no args) to list recipes.
#
# Recipes go through `uv run`, which always targets this project's own .venv.
# This repo owns filling ORCID_JSON/; other repos call `just prefetch` here
# (tamu-coe-faculty-profiles: `just prefetch`, academia-openalex: `just prefetch`).

python := "uv run python"
db := env("COE_DATA_DB", justfile_directory() / "../coe-data-db/en.db")

# List available recipes.
default:
    @just --list

# Fill ORCID_JSON/ (missing or stale records only).
# Scope with --dept CODE / --uin UIN / --uin-file PATH; --force refetches; --dry-run lists.
prefetch *args:
    {{ python }} run_prefetch.py --mapping-db {{ db }} {{ args }}
