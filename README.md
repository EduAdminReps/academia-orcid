# academia-orcid

Fetches academic publication and employment data from ORCID and generates LaTeX/JSON sections for faculty vita reports. Institution-agnostic — works with any UIN→ORCID mapping database.

## Quick Start

```bash
# Install in development mode
pip install -e .

# Generate publications section (using ORCID ID directly)
python run_latex.py --orcid 0000-0003-0831-6109 --output-dir ./out

# Generate ORCID data section (employment, education, etc.)
python run_latex.py --orcid 0000-0003-0831-6109 --output-dir ./out --section data

# Using UIN (requires SQLite mapping database)
python run_latex.py --uin 123456789 --output-dir ./out --mapping-db /path/to/shared.db

# JSON output (same CLI contract)
python run_json.py --orcid 0000-0003-0831-6109 --output-dir ./out

# With year filter
python run_latex.py --orcid 0000-0003-0831-6109 --output-dir ./out --year 2020-2025
```

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
│       └── schema.py             # TypedDict definitions for ORCID v3.0 JSON
├── tests/                        # Test directory
├── tools/                        # Standalone analysis scripts (not part of pipeline)
├── ORCID_JSON/                   # Cached ORCID records (gitignored)
├── outputs/                      # Generated output files (gitignored)
├── run_latex.py                  # Thin wrapper for composer compatibility (LaTeX)
├── run_json.py                   # Thin wrapper for composer compatibility (JSON)
├── pyproject.toml                # Package configuration (src layout)
└── .gitignore
```

## CLI Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--uin` | Yes* | — | Faculty UIN (*mutually exclusive with `--orcid`) |
| `--orcid` | Yes* | — | ORCID ID directly |
| `--output-dir` | Yes | — | Output directory for .tex/.json files |
| `--data-dir` | No | `.` | Base directory containing ORCID data |
| `--section` | No | `publications` | Section type: `publications` or `data` |
| `--year` | No | — | Year filter (ignored for data section) |
| `--fetch` | No | Yes | Fetch from API if not cached |
| `--no-fetch` | No | — | Only use cached records |
| `--force-fetch` | No | — | Always fetch from API |
| `--mapping-db` | Yes** | — | Path to SQLite database with `orcid_mapping` table (**required when using `--uin`) |

## Dependencies

```
requests        # ORCID API calls
```

## Credits

Uses [ORCID Public API v3.0](https://info.orcid.org/documentation/integration-guide/orcid-public-api-v3-0/).
