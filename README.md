# academia-orcid

Fetches academic publication and employment data from ORCID and generates LaTeX/JSON sections for faculty vita reports. Institution-agnostic — works with any UIN→ORCID mapping database.

Can also produce **standalone CVs** (PDF, Word, or BibTeX) directly from an ORCID ID.

## Standalone CV Generation

Generate a complete CV from any ORCID ID — no database or composer required.

```bash
# PDF (via LaTeX)
python tools/compose_cv.py --orcid 0000-0002-2983-9884

# Word document
python tools/compose_cv.py --orcid 0000-0002-2983-9884 --format docx

# BibTeX bibliography
python tools/compose_cv.py --orcid 0000-0002-2983-9884 --format bibtex

# BibTeX with DOI enrichment (fills volume, pages, etc.)
python tools/compose_cv.py --orcid 0000-0002-2983-9884 --format bibtex --enrich

# Filter publications by year
python tools/compose_cv.py --orcid 0000-0002-2983-9884 --cal_year 2020-2025

# LaTeX source only (no compilation)
python tools/compose_cv.py --orcid 0000-0002-2983-9884 --skip-compile
```

Output goes to `out_cv/{orcid-id}/`. PDF requires `pdflatex`; DOCX requires `pip install python-docx`.

## Section Generation (Composer Interface)

When used as a section provider for the parent composer, this package produces `.tex` and `.json` fragments:

```bash
pip install -e .

# Publications section
python run_latex.py --orcid 0000-0002-2983-9884 --output-dir ./out

# ORCID data section (employment, education, etc.)
python run_latex.py --orcid 0000-0002-2983-9884 --output-dir ./out --section data

# JSON output
python run_json.py --orcid 0000-0002-2983-9884 --output-dir ./out

# Using UIN (requires mapping database)
python run_latex.py --uin 123456789 --output-dir ./out --mapping-db /path/to/en.db

# Year filter
python run_latex.py --orcid 0000-0002-2983-9884 --output-dir ./out --cal_year 2020-2025
```

## Bulk Cache Fill

Download every mapped faculty member's ORCID record into `ORCID_JSON/` ahead of
time, so report runs can pass `--no-fetch` and never wait on the API:

```bash
just prefetch                          # missing or stale (> 7 days) records
just prefetch --dry-run                # list what would be downloaded
just prefetch --force                  # refresh everything
just prefetch --dept MEEN              # current faculty of one department (repeatable)
just prefetch --uin 123456789          # one person (repeatable); or --uin-file PATH
```

Fresh records are skipped, so an interrupted run can be rerun to resume. Exit
code 1 means at least one record failed to download (the rest are kept).

## Project Structure

```
academia-orcid/
├── src/academia_orcid/             # Installable Python package
│   ├── cli.py                      # Section-provider entry point
│   ├── fetch.py                    # ORCID API client and caching
│   ├── prefetch.py                 # Bulk cache fill for every mapped ORCID
│   ├── extract.py                  # Data extraction from ORCID records
│   ├── latex.py                    # LaTeX generation
│   ├── json_export.py              # JSON export
│   ├── bibtex_export.py            # BibTeX export
│   ├── enrich.py                   # DOI content negotiation enrichment
│   ├── normalize.py                # Text normalization (HTML, LaTeX, Unicode)
│   └── schema.py                   # ORCID v3.0 TypedDict definitions
├── tools/                          # Standalone CV tools
│   ├── compose_cv.py               # CV generator (--format latex | docx | bibtex)
│   ├── docx_formatter.py           # ORCID-only Word formatter
│   └── templates/                  # LaTeX templates for standalone CV
├── tests/                          # Test suite
├── run_latex.py                    # Composer entry point (LaTeX)
├── run_json.py                     # Composer entry point (JSON)
├── run_bibtex.py                   # Composer entry point (BibTeX)
├── run_prefetch.py                 # Bulk cache fill (wrapper for prefetch.py)
└── pyproject.toml
```

## Section-Provider CLI Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--uin` | Yes* | — | Faculty UIN (*mutually exclusive with `--orcid`) |
| `--orcid` | Yes* | — | ORCID ID directly |
| `--output-dir` | Yes | — | Output directory for .tex/.json files |
| `--section` | No | `publications` | Section type: `publications` or `data` |
| `--year` / `--acad_year` / `--cal_year` / `--semester` | No | all years | Report period for publications (ignored for data section). `--year` is a fiscal year (Fall Y−1 + Spring Y); forms `2024`, `2020-2025`, `2020+`, `all` |
| `--fetch` / `--no-fetch` / `--force-fetch` | No | `--fetch` | ORCID API fetch control |
| `--mapping-db` | Yes** | — | SQLite database with `orcid_mapping` table (**required with `--uin`) |

## Dependencies

```
requests        # ORCID API calls
python-docx     # Word output (optional, only for tools/compose_cv.py --format docx)
pdflatex        # PDF compilation (optional, system requirement)
```

## Credits

Uses [ORCID Public API v3.0](https://info.orcid.org/documentation/integration-guide/orcid-public-api-v3-0/).
