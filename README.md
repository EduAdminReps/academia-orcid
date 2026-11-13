# academia-orcid

Fetches faculty members' ORCID records and extracts them into structured JSON —
publications and profile data — for the College of Engineering faculty composer
(`tamu-coe-faculty-profiles`), which renders them. Institution-agnostic: works with
any UIN → ORCID mapping database.

## Usage

```bash
uv sync

# Publications (default section)
python run_json.py --orcid 0000-0002-2983-9884 --output-dir ./out

# Profile data (employment, education, distinctions, ...)
python run_json.py --orcid 0000-0002-2983-9884 --output-dir ./out --section data

# By UIN, through the mapping database; a period for publications
python run_json.py --uin 123456789 --mapping-db ../coe-data-db/en.db --output-dir ./out --cal_year 2020-2025
```

Writes `orcid-publications.json` or `orcid-data.json`; nothing when there is no
data. `--fetch` (default), `--no-fetch` or `--force-fetch` control the ORCID API.

## Bulk cache fill

```bash
just prefetch                          # missing or stale (> 7 days) records
just prefetch --dry-run                # list what would be downloaded
just prefetch --force                  # refresh everything
just prefetch --dept MEEN              # current faculty of one department (repeatable)
just prefetch --uin 123456789          # one person (repeatable); or --uin-file PATH
```

Fresh records are skipped, so an interrupted run can be rerun to resume. Exit
code 1 means at least one record failed to download (the rest are kept).

## Development

```bash
just test        # pytest
just lint        # ruff check + ruff format --check
just typecheck   # mypy
just check       # all three
```

See `CLAUDE.md` for the JSON shape, the extraction rules and the CLI contract.

## Credits

Uses the [ORCID Public API v3.0](https://info.orcid.org/documentation/integration-guide/orcid-public-api-v3-0/).
