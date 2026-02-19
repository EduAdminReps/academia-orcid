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
python tools/compose_cv.py --orcid 0000-0002-2983-9884 --year 2020-2025

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
python run_latex.py --uin 123456789 --output-dir ./out --mapping-db /path/to/shared.db

# Year filter
python run_latex.py --orcid 0000-0002-2983-9884 --output-dir ./out --year 2020-2025
```

## Project Structure

```
academia-orcid/
├── src/academia_orcid/             # Installable Python package
│   ├── cli.py                      # Section-provider entry point
│   ├── fetch.py                    # ORCID API client and caching
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
└── pyproject.toml
```

## Section-Provider CLI Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--uin` | Yes* | — | Faculty UIN (*mutually exclusive with `--orcid`) |
| `--orcid` | Yes* | — | ORCID ID directly |
| `--output-dir` | Yes | — | Output directory for .tex/.json files |
| `--section` | No | `publications` | Section type: `publications` or `data` |
| `--year` | No | — | Year filter (ignored for data section) |
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
