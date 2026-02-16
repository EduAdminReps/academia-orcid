# CLAUDE.md — academia-orcid

## Purpose

This package fetches academic publication and employment data from ORCID (Open Researcher and Contributor ID) and generates LaTeX/JSON sections for faculty vita reports. It is institution-agnostic — any university can use it by providing a UIN→ORCID mapping database.

## Vita Sections Covered

| Section | Name | Output File |
|---------|------|-------------|
| 9 | Publications | `orcid-publications.tex` / `orcid-publications.json` |
| — | ORCID Data (external info) | `orcid-data.tex` / `orcid-data.json` |

## Project Structure

```
academia-orcid/
├── src/
│   └── academia_orcid/           # Installable Python package
│       ├── __init__.py           # Package constants and version
│       ├── cli.py                # Main entry point (argparse + orchestration)
│       ├── extract.py            # Data extraction from ORCID records
│       ├── latex.py              # LaTeX generation (publications + data sections)
│       ├── json_export.py        # JSON export (publications + data sections)
│       ├── normalize.py          # Text normalization (HTML, LaTeX, Unicode)
│       ├── fetch.py              # ORCID API client, caching, UIN mapping
│       └── schema.py             # TypedDict definitions for ORCID JSON
├── tests/                        # Test directory
├── ORCID_JSON/                   # Cached ORCID records (gitignored)
├── outputs/                      # Generated output files (gitignored)
├── tools/                        # Standalone analysis scripts (not part of pipeline)
├── run_latex.py                  # Thin wrapper for composer compatibility (LaTeX)
├── run_json.py                   # Thin wrapper for composer compatibility (JSON)
├── pyproject.toml                # Package configuration (src layout)
└── .gitignore
```

## Data Source

**ORCID Public API v3.0** — Fetches data using faculty ORCID IDs.

Schema documentation: [src/academia_orcid/schema.py](src/academia_orcid/schema.py)

### Data Flow

1. Faculty UIN → ORCID mapping loaded from SQLite (table `orcid_mapping`) via `--mapping-db` (required when using `--uin`)
2. ORCID records cached in `ORCID_JSON/{orcid}.json` (fetched via `--fetch`/`--force-fetch` flags)
3. `run_latex.py` (thin wrapper) → `academia_orcid.cli.main()` extracts data and generates LaTeX output
4. `run_json.py` (thin wrapper) → exports structured JSON for YAML/Word pipelines

## Package Modules

| Module | Purpose |
|--------|---------|
| `academia_orcid.cli` | `main()` entry point — argparse, orchestration |
| `academia_orcid.fetch` | ORCID API client, JSON cache loading, UIN→ORCID mapping |
| `academia_orcid.extract` | Publication/data extraction, year filtering |
| `academia_orcid.latex` | LaTeX generation (`escape_latex`, `generate_latex`, `generate_data_latex`) |
| `academia_orcid.json_export` | JSON export (`export_publications`, `export_data`) |
| `academia_orcid.normalize` | Text normalization (HTML→LaTeX, plaintext cleaning) |
| `academia_orcid.schema` | TypedDict definitions for ORCID v3.0 JSON structure |

## Root Scripts

| Script | Purpose |
|--------|---------|
| `run_latex.py` | **Composer entry point** — thin wrapper calling `academia_orcid.cli.main()` |
| `run_json.py` | **Composer entry point** — JSON export for YAML/Word pipelines |

## CLI Interface

```bash
# Generate publications section (default)
python run_latex.py --uin <uin> --output-dir ./out --mapping-db /path/to/shared.db
# Produces: ./out/orcid-publications.tex

# Generate ORCID data section (employment, memberships, etc.)
python run_latex.py --uin <uin> --output-dir ./out --mapping-db /path/to/shared.db --section data
# Produces: ./out/orcid-data.tex

# JSON output (same CLI contract)
python run_json.py --uin <uin> --output-dir ./out --mapping-db /path/to/shared.db
# Produces: ./out/orcid-publications.json

# With year filter (publications only)
python run_latex.py --uin <uin> --output-dir ./out --mapping-db /path/to/shared.db --year 2024-2025

# Using ORCID ID directly (bypasses UIN→ORCID mapping)
python run_latex.py --orcid 0000-0003-0831-6109 --output-dir ./out

# Force-refresh cached ORCID record from API
python run_latex.py --uin <uin> --output-dir ./out --mapping-db /path/to/shared.db --force-fetch

# All options
python run_latex.py [--uin <uin> --mapping-db <path> | --orcid <orcid>] --output-dir <path> [--data-dir <path>] [--section {publications,data}] [--year <year>] [--fetch | --no-fetch | --force-fetch]
```

### Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--uin` | Yes* | — | Faculty UIN (*mutually exclusive with `--orcid`) |
| `--orcid` | Yes* | — | ORCID ID directly, bypasses UIN→ORCID mapping (*mutually exclusive with `--uin`) |
| `--output-dir` | Yes | — | Output directory for .tex/.json files |
| `--data-dir` | No | `.` | Base directory containing ORCID data |
| `--section` | No | `publications` | Section type: `publications` or `data` |
| `--year` | No | — | Year filter for publications (ignored for data section) |
| `--fetch` | No | Yes | Fetch ORCID record from API if not in cache (default behavior) |
| `--no-fetch` | No | — | Only use cached records, do not fetch from API |
| `--force-fetch` | No | — | Always fetch from API, even if cached record exists (refreshes cache) |
| `--mapping-db` | Yes** | — | Path to SQLite database with `orcid_mapping` table (**required when using `--uin`) |

**Year Format:**
- `YYYY-YYYY`: Year range (e.g., `2020-2025`)
- `YYYY`: Single year (e.g., `2024`, treated as `2024-2024`)
- `all`: Include all available data (no filtering)
- Omitted: Same as `all`

**Year Filter Behavior:**
- **`--section publications`**: Filters publications by publication year. Only works with years in the specified range are included.
- **`--section data`**: The `--year` parameter is **ignored**. All employment, education, membership, etc. data is always included regardless of dates.

## Section: Publications

Extracts works from ORCID record and categorizes by type:

**Journal Articles:** `journal-article`, `journal-issue`, `article-journal`

**Conference Papers:** `conference-paper`, `conference-abstract`, `conference-poster`, `paper-conference`

**Other:** books, chapters, reports, dissertations, etc.

Output includes DOI links where available.

## Section: Data

Extracts non-publication ORCID data:

| Subsection | ORCID Path |
|------------|------------|
| Biography | `person/biography` |
| Employment | `activities-summary/employments` |
| Education | `activities-summary/educations` |
| Selected Projects | `activities-summary/fundings` |
| External Identifiers | `person/external-identifiers` (Scopus, ResearcherID) |
| Distinctions | `activities-summary/distinctions` |
| Memberships | `activities-summary/memberships` |
| External Service | `activities-summary/services` |

Each subsection only appears if data exists.

## UIN → ORCID Mapping

The package requires a SQLite database with an `orcid_mapping` table:

| Column | Description |
|--------|-------------|
| `UIN` | Faculty identifier |
| `ORCID` | ORCID ID (e.g., `0000-0003-0831-6109`) |

The mapping database path is passed via `--mapping-db`. Alternatively, use `--orcid` to bypass the mapping entirely.

## Dependencies

```
requests        # ORCID API calls
```

Install the package in development mode: `pip install -e .`

## Notes

- ORCID API has rate limits — scripts implement delays and retries
- Unicode handling via `html.unescape()` for international characters
- LaTeX special characters escaped automatically
- DOI links preserved and formatted as hyperlinks
- Year filtering supported via `--year` flag (range, single year, or `all`)
