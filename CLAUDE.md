# CLAUDE.md — academia-orcid

## Purpose

This package fetches academic publication and employment data from ORCID (Open Researcher and Contributor ID) and generates LaTeX/JSON sections for faculty vita reports. It is institution-agnostic — any university can use it by providing a UIN→ORCID mapping database.

## Data Philosophy

**ORCID as system of record.** Faculty are asked to maintain their ORCID profiles as a proxy for submitting annual CVs. All generated outputs (LaTeX/PDF, the JSON behind the composer's Word report, BibTeX) are faithful renderings of that record. If a report entry is questioned, the answer is always "this is what's in the faculty member's ORCID profile." This creates a clean accountability boundary — the faculty member owns the data, the tool renders it.

**Hierarchical enrichment.** ORCID data is the baseline for all outputs. External metadata sources — DOI content negotiation (`https://doi.org/{doi}` with `Accept: application/x-bibtex`), Crossref API, DataCite — may fill gaps (volume, pages, number) but never override ORCID-provided fields (title, authors, type, venue). Enrichment is always opt-in (e.g., `--enrich` flag), not automatic. The default output reflects ORCID data only.

**Known metadata quality limitations.** These are inherent source-data limitations, not bugs:
- *Names*: Both ORCID and Crossref reflect what publishers submitted. Older records and certain publishers (e.g., IEEE) store initials only, not full given names. No automated reconciliation is feasible.
- *Entry types*: Publishers frequently register conference papers as `journal-article` (because proceedings volumes get ISSNs). ORCID's `type` field has the same source-quality problem.
- *Older DOIs*: Pre-2005 Crossref records are often skeletal. The structured metadata schema evolved over time; publishers are not obligated to back-fill.
- *Missing DOIs*: Conference papers, book chapters, technical reports, and non-English publications often lack DOIs entirely. For these, ORCID data is the only source.

The tool renders what the sources provide. If a faculty member wants richer output, the primary answer is "add more detail to your ORCID record." The secondary answer is "use enrichment and review the result."

**Accountability boundary.** The standalone CV tool accepts `--orcid` (not `--uin`) because the ORCID ID is the faculty member's identifier in this workflow. University-specific UIN→ORCID mapping is an institutional concern handled by the parent composer.

## Vita Sections Covered

| Section | Name | Output File |
|---------|------|-------------|
| 9 | Publications | `orcid-publications.tex` (+ `orcid-publications-summary.tex`) / `orcid-publications.json` |
| — | ORCID Data (external info) | `orcid-data.tex` / `orcid-data.json` |

**Fragments carry no `\section`** (the faculty-profiles section contract): the
composer template writes the "ORCID Data" and "ORCID Publications" headings and
inputs `orcid-publications-summary.tex` (profile link, counts by type) under the
second. Each fragment starts at subsection level (audit ORC-03; tamu-scholars
does the same).

## Project Structure

```
academia-orcid/
├── src/
│   └── academia_orcid/           # Installable Python package
│       ├── __init__.py           # Package constants and version
│       ├── cli.py                # run_latex entry point; flags, lookup and record load shared with run_json/run_bibtex
│       ├── extract.py            # Data extraction from ORCID records
│       ├── latex.py              # LaTeX generation (publications + data sections)
│       ├── json_export.py        # JSON export (publications + data sections)
│       ├── bibtex_export.py       # BibTeX export from ORCID publication data
│       ├── enrich.py             # DOI content negotiation enrichment (opt-in)
│       ├── normalize.py          # Text normalization (HTML, LaTeX, Unicode), from latex_text
│       ├── latex_text.py         # Vendored coe_core.latex (escaping, HTML to LaTeX); never edit here
│       ├── periods.py            # Vendored coe_core.periods (the period flags); never edit here
│       ├── fetch.py              # ORCID API client, caching, UIN mapping
│       ├── prefetch.py           # Bulk cache fill for every mapped ORCID (run_prefetch.py)
│       ├── config.py             # YAML configuration management (optional pyyaml)
│       ├── logging_config.py     # Logging setup and module logger factory
│       └── schema.py             # TypedDict definitions for ORCID JSON
├── tests/                        # Test directory
├── tools/                        # Standalone CV tool
│   ├── compose_cv.py             # Standalone ORCID CV generator (LaTeX/PDF, BibTeX)
│   └── templates/                # LaTeX templates for standalone CV
│       ├── preamble.tex          # Minimal preamble (no tikz/pgfplots)
│       ├── header.tex.template   # Faculty header template
│       └── main.tex.template     # Main document (ORCID sections only)
├── tools_local/                  # Local analysis scripts (gitignored)
├── ORCID_JSON/                   # Cached ORCID records (gitignored)
├── outputs/                      # Generated output files (gitignored)
├── out_cv/                       # Standalone CV output (gitignored)
├── run_latex.py                  # Thin wrapper for composer compatibility (LaTeX)
├── run_json.py                   # Thin wrapper for composer compatibility (JSON)
├── run_bibtex.py                 # Thin wrapper for composer compatibility (BibTeX)
├── run_prefetch.py               # Bulk cache fill (thin wrapper for academia_orcid.prefetch)
├── justfile                      # `just prefetch` (the one way to fill ORCID_JSON/), test, lint, typecheck, format, check
├── pyproject.toml                # Package configuration (src layout)
└── .gitignore
```

## Data Source

**ORCID Public API v3.0** — Fetches data using faculty ORCID IDs.

Schema documentation: [src/academia_orcid/schema.py](src/academia_orcid/schema.py)

### Data Flow

1. Faculty UIN → ORCID looked up in SQLite (en.db's `faculty_identifiers`, Scheme `orcid`) via `--mapping-db` (required when using `--uin`)
2. ORCID records cached in `ORCID_JSON/{orcid}.json` (fetched via `--fetch`/`--force-fetch` flags)
3. `run_latex.py` (thin wrapper) → `academia_orcid.cli.main()` extracts data and generates LaTeX output
4. `run_json.py` (thin wrapper) → exports structured JSON for YAML/Word pipelines

## Package Modules

| Module | Purpose |
|--------|---------|
| `academia_orcid.cli` | `main()` (run_latex), and what all three entry points share: `add_common_args`, `resolve_orcid_id`, `load_record`, `resolve_period` (one set of flags and exit codes) |
| `academia_orcid.fetch` | ORCID API client, JSON cache (whole-file writes, partial records stale), UIN→ORCID mapping |
| `academia_orcid.prefetch` | Bulk cache fill: every ORCID in `faculty_identifiers` → `ORCID_JSON/` |
| `academia_orcid.extract` | Publication/data extraction, year filtering |
| `academia_orcid.latex` | LaTeX generation (`escape_latex`, `generate_latex`, `generate_latex_summary`, `generate_data_latex`) |
| `academia_orcid.json_export` | JSON export (`export_publications`, `export_data`) |
| `academia_orcid.bibtex_export` | BibTeX export (embedded ORCID BibTeX preferred, generated fallback; unique keys) |
| `academia_orcid.enrich` | DOI content negotiation enrichment (opt-in, fill-only semantics) |
| `academia_orcid.normalize` | Text normalization (HTML→LaTeX, plaintext cleaning) |
| `academia_orcid.config` | YAML configuration management (`Config` class, `get_config()`, env overrides) |
| `academia_orcid.logging_config` | Logging setup (`setup_logging()`, `get_logger()`) |
| `academia_orcid.schema` | TypedDict definitions for ORCID v3.0 JSON structure |

## Root Scripts

| Script | Purpose |
|--------|---------|
| `run_latex.py` | **Composer entry point** — thin wrapper calling `academia_orcid.cli.main()` |
| `run_json.py` | **Composer entry point** — JSON export for YAML/Word pipelines |
| `run_bibtex.py` | **Composer entry point** — BibTeX export for publications |
| `run_prefetch.py` | Bulk cache fill — downloads every mapped ORCID record (see Bulk Cache Fill) |

## Bulk Cache Fill

`run_latex.py`/`run_json.py` fetch one record on demand, and treat a cached
record older than the TTL (7 days) as stale. `just prefetch` fills
`ORCID_JSON/` for every ORCID in `faculty_identifiers` ahead of time, so the composer
can run with `--no-fetch` and make no live API calls. **This repo owns its
cache:** `tamu-coe-faculty-profiles` and `academia-openalex` call this recipe
(`just prefetch` in each) rather than fetching on their own.

```bash
just prefetch                          # missing or stale records (en.db: $COE_DATA_DB or ../coe-data-db/en.db)
just prefetch --dry-run                # report only
just prefetch --force                  # refresh everything
just prefetch --dept MEEN              # current faculty of a department (latest faculty_census term; repeatable)
just prefetch --uin 123456789          # one person (repeatable)
just prefetch --uin-file nominees.txt  # one UIN per line (# comments ok), or a CSV with a UIN column
```

The scope options combine as a union; a scope that matches nobody fetches
nothing (never "everyone"), and an unknown department is an error.

- Fresh complete records are skipped; each record is written whole (a temporary file renamed over the old one), so an interrupted run resumes on rerun and never leaves a truncated file (audit ORC-09).
- One person at a time (`--delay`, default 0.2 s between people); works within a person use the existing concurrent fetch.
- A work whose detail call fails (429 after retries, 5xx, network) keeps its summary, which has no contributors. The count is recorded in `_cache_metadata` (`missing_work_details`), the record counts as stale, and the next fetch or prefetch tries again (`partial`).
- Per-person outcome on stderr, then a summary (`fetched`, `partial` = some work details missing, `fresh`, `failed`, `invalid`). Exit 1 if any fetch failed; an en.db without `faculty_identifiers` exits 1 with a message.
- Rough cost: ~6 works/s, so ~290 COE ORCIDs take about an hour.

## CLI Interface

```bash
# Generate publications section (default)
python run_latex.py --uin <uin> --output-dir ./out --mapping-db /path/to/en.db
# Produces: ./out/orcid-publications.tex

# Generate ORCID data section (employment, memberships, etc.)
python run_latex.py --uin <uin> --output-dir ./out --mapping-db /path/to/en.db --section data
# Produces: ./out/orcid-data.tex

# JSON output (same CLI contract)
python run_json.py --uin <uin> --output-dir ./out --mapping-db /path/to/en.db
# Produces: ./out/orcid-publications.json

# With a period (publications only): calendar years 2024 through 2025
python run_latex.py --uin <uin> --output-dir ./out --mapping-db /path/to/en.db --cal_year 2024-2025

# Using ORCID ID directly (bypasses UIN→ORCID mapping)
python run_latex.py --orcid 0000-0002-2983-9884 --output-dir ./out

# Force-refresh cached ORCID record from API
python run_latex.py --uin <uin> --output-dir ./out --mapping-db /path/to/en.db --force-fetch

# All options
python run_latex.py [--uin <uin> --mapping-db <path> | --orcid <orcid>] --output-dir <path> [--data-dir <path>] [--section {publications,data}] [--year | --acad_year | --cal_year | --semester <value>] [--fetch | --no-fetch | --force-fetch]
```

### Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--uin` | Yes* | — | Faculty UIN (*exactly one of `--uin`, `--orcid`; both is an error) |
| `--orcid` | Yes* | — | ORCID ID directly, bypasses UIN→ORCID mapping |
| `--output-dir` | Yes | — | Output directory for .tex/.json files |
| `--data-dir` | No | `.` | Base directory containing ORCID data |
| `--section` | No | `publications` | Section type: `publications` or `data` |
| `--year` / `--acad_year` / `--cal_year` / `--semester` | No | all years | Report period for publications (ignored for data section); one of the four |
| `--fetch` | No | Yes | Fetch ORCID record from API if not in cache (default behavior) |
| `--no-fetch` | No | — | Only use cached records, do not fetch from API |
| `--force-fetch` | No | — | Always fetch from API, even if cached record exists (refreshes cache) |
| `--mapping-db` | Yes** | — | Path to SQLite database (en.db) with the `faculty_identifiers` table (**required when using `--uin`) |

**Period flags** (`academia_orcid.periods`, a verbatim copy of coe-data-core's
`coe_core.periods`, written by its `just vendor-set`; never edit it here):
- `--year Y`: fiscal year, Fall Y−1 + Spring Y. **`--year 2024` is no longer calendar 2024.**
- `--acad_year Y`: Fall Y−1 + Spring Y + Summer Y.
- `--cal_year Y`: Spring + Summer + Fall Y.
- `--semester YYYYSC`: one term (e.g. `202431`).
- Forms: `2024`, `2020-2025` (range), `2020+` (open-ended), `all`; for `--semester`, `202431`, `202331-202521`, `202331+`, `all`.
- No flag: all years. A malformed value exits 1 with a message.

**Exit codes** (all three entry points; `academia_orcid.cli`): 0 done, with or
without data; 1 bad input (malformed id or period, no `--mapping-db`, an en.db
without `faculty_identifiers`, i.e. older than schema v17); 2 argparse errors, a
fetch that failed with nothing cached, and `--no-fetch` with nothing cached.

**Filter Behavior:**
- **`--section publications`** (owner, 2026-11-12): a publication dated by a month is kept when that month's term is in the period (`Period.overlaps_date`: January–May spring, June–July summer, August–December fall); one with only a year when that calendar year overlaps it (so `--year 2024` keeps any 2024 work, and a 2023 work only if dated August–December). A publication with no or an unparseable year is left out of every period report and shown only in all-years reports (no flag, or `all`).
- **`--section data`**: The period is **ignored**. All employment, education, membership, etc. data is always included regardless of dates.

## Section: Publications

Extracts works from ORCID record and categorizes by type:

**Journal Articles:** `journal-article`, `journal-issue`, `article-journal`

**Conference Papers:** `conference-paper`, `conference-abstract`, `conference-poster`, `paper-conference`

**Other:** books, chapters, reports, dissertations, etc.

Output includes DOI links where available.

**One entry per work.** ORCID groups works by shared identifiers only, so a
work imported once with a DOI and once without lands in two groups.
`extract.collapse_duplicates` keeps one entry per work: same DOI (case-insensitive),
or, when either lacks one, the same type, title (at least 20 letters and digits,
so "Editorial" never matches) and year. The DOI-bearing copy wins, then journal
over conference over other (owner, 2026-11-12).

**DOIs** are stored bare (`10.xxxx/...`, URL and `doi:` prefixes stripped;
`extract.normalize_doi`). Only the work's own DOI is used (relationship `self`, or
none given); a chapter whose only DOI is its book's (`part-of`) shows no DOI.

**Authors** are shown "Family, F.M." (IEEE style) whatever the credit-name order:
`extract.split_name` reads "Given Family", "Family, Given" (56% of the cache) and
"Family F", "Family Given F" (trailing initials). BibTeX uses the same split.

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

The package reads en.db's `faculty_identifiers` table (built by coe-data-core; one
row per identifier, for ORCID, Scholars@TAMU, Google Scholar and OpenAlex). It uses
only the rows with Scheme `orcid`, at most one per person:

| Column | Description |
|--------|-------------|
| `UIN` | Faculty identifier |
| `Scheme` | `orcid` (other schemes are ignored) |
| `Identifier` | ORCID ID (e.g., `0000-0002-2983-9884`) |

The lookup takes the person's lowest-`Rank` `orcid` row, whitespace stripped (the
schema allows several ranks; today every person has one). The table name and
scheme are `IDENTIFIERS_TABLE` / `ORCID_SCHEME` in `fetch.py` (this repo does not
import coe-data-core). It replaced `orcid_mapping` (2026-11-09). The cache is flat,
`ORCID_JSON/{orcid}.json` (academia-openalex reads it too).
The mapping database path is passed via `--mapping-db`. Alternatively, use `--orcid` to bypass the mapping entirely.

## Dependencies

```
requests        # ORCID API calls
pyyaml          # Optional: YAML config file support (falls back to defaults if absent)
```

Install with `uv sync` (the dev group adds pytest, ruff and mypy). Checks:
`just test`, `just lint` (ruff check + `ruff format --check`), `just typecheck`
(mypy; settings in pyproject.toml), `just check` (all three).

### Configuration

Optional YAML config file (`.academia-orcid.yaml`) searched in: `./`, `~/`, `/etc/academia-orcid/`. Supports API tuning (base URL, timeouts, rate limits), cache settings, and output options. Environment variable overrides: `ORCID_API_BASE_URL`, `ORCID_CACHE_TTL`, `ORCID_API_TIMEOUT`. See [.academia-orcid.yaml.example](.academia-orcid.yaml.example) for format.

## Standalone CV Tool

This repo can independently produce complete CVs from ORCID data alone, without requiring the parent `tamu-coe-faculty-profiles` composer or its privileged data sources.

### Rationale

ORCID data is public, unlike the other data sources aggregated by the parent composer (SET evaluations, funding, service records, awards). This standalone tool allows anyone with an ORCID ID to generate a formatted CV without access to the full composer infrastructure.

### CLI

The standalone tool accepts only `--orcid` as input — university-specific UIN lookups are handled by the parent composer.

```bash
# LaTeX/PDF (default)
python tools/compose_cv.py --orcid 0000-0002-2983-9884
python tools/compose_cv.py --orcid 0000-0002-2983-9884 --cal_year 2020-2025
python tools/compose_cv.py --orcid 0000-0002-2983-9884 --skip-compile

# BibTeX
python tools/compose_cv.py --orcid 0000-0002-2983-9884 --format bibtex

# DOI enrichment (fills volume, pages, etc. from DOI metadata)
python tools/compose_cv.py --orcid 0000-0002-2983-9884 --format bibtex --enrich

# Other options: --output-dir, --data-dir, --fetch/--no-fetch/--force-fetch, --dry-run
```

Output goes to `out_cv/{orcid-id}/` by default:
- LaTeX: `{orcid-id}-cv.pdf`, `{orcid-id}-source.zip`, and `.tex` source files
- BibTeX: `{orcid-id}.bib`

Each run first removes the previous run's fragments, PDF, archive (or `.bib`) and
`main.*` byproducts, and nothing else, so a rerun for an empty period never shows
an older list, and `--output-dir` may point at a folder holding other files (audit
ORC-08). The archive holds only this run's sources. Exit codes: 0 done; 1 bad input
or failed compilation; 2 no record (fetch failed with nothing cached, or
`--no-fetch` with nothing cached).

Word output was retired on 2026-11-12 (owner): the faculty-profiles Word report
renders through EN_Templates, and its ORCID renderers, which `tools/docx_formatter.py`
was copied from, no longer exist.

### Provenance

`tools/compose_cv.py` and `tools/templates/` were adapted from the parent
composer's `compose_latex.py` (compilation, archiving) and `templates/`
(`preamble.tex` without tikz/pgfplots; `header.tex.template` with the `%%key%%`
placeholders compose_cv fills; `main.tex.template` with the ORCID sections only).
They are maintained here and no longer synced: the parent has moved on, and this
tool keeps only what an ORCID-only CV needs.

### Relationship to Section-Provider Role

The standalone CV tools (`tools/`) are **independent** of the section-provider interface. The composer entry points (`run_latex.py`, `run_json.py`) remain unchanged and continue to produce `.tex`/`.json` fragments as before. The tools reuse the same package modules (`academia_orcid.fetch`, `academia_orcid.extract`, etc.) but add the "last mile" — template generation, compilation, and document assembly — that was previously only available through the parent composer.

### Dependencies

- `pdflatex` (TeX Live or MacTeX) is required for PDF compilation. Use `--skip-compile` to generate LaTeX source without compiling.

## Twin repository (tamu-scholars)

`../tamu-scholars/` is this repo's twin for Scholars@TAMU: another source, the same
section contract. Their shared code is of two kinds:

- **Vendored** from coe-data-core (one source, drift-tested there): `periods.py`
  and `latex_text.py`. Never edit them here; change coe-data-core and run its
  `just vendor-set`.
- **Hand-aligned copies** (owner, 2026-11-12: two copies for now, no drift test):
  - `cli.py`: the common flags (`--uin`/`--orcid` exclusive, the fetch group),
    `resolve_period`, the id lookup and `load_record`, the exit codes;
  - `fetch.py`: the whole-file cache write, the en.db lookup (lowest Rank,
    stripped), and the rule that a record with missing details is partial;
  - `prefetch.py`: the scope options, outcome counts and exit code;
  - `config.py` (validated after the environment overrides) and `logging_config.py`;
  - `extract.py`: `filter_publications_by_period` and `collapse_duplicates`;
  - the summary format (`Journal Articles: 12`), and the justfile recipes and
    ruff/mypy settings.

  A change to any of these is checked against the twin and made there too, unless
  it is source-specific (ORCID work details vs Scholars documents and 404s). If a
  fix again lands in one twin only, revisit: vendor the source-neutral parts from
  coe-data-core like `latex_text.py`.

  **A third copy** (owner, 2026-11-13): `../academia-openalex/` lists the works
  OpenAlex attributes to an author id with the same contract (`run_json.py` only;
  its `section_cli.py` is this repo's `cli.py`). Check changes to the shared parts
  against it too.

**Provenance** (owner, 2026-11-13): the publications JSON carries
`_meta.provenance` = `{source: "orcid", ids: [orcid], curation: "author-curated",
fetched_at: <cache time>}`. tamu-scholars and academia-openalex write the same keys
(OpenAlex: `curation: "aggregated"`), so a consumer tells curated lists from
aggregated ones the same way.

## Notes

- ORCID API has rate limits — scripts implement delays and retries
- Unicode handling via `html.unescape()` for international characters
- LaTeX special characters escaped automatically
- **Escaping is shared** with tamu-scholars: `latex_text.py` is a verbatim copy of coe-data-core's `coe_core.latex` (written by its `just vendor-set`, drift-tested there; never edit it here). `escape_latex()` (structured fields) and `escape_latex_smart()` (titles, biography: HTML tags with their nesting kept, `$...$` math kept only if base LaTeX can set it) keep every character pdflatex sets with the report preamble — Latin-1, Latin Extended-A, dashes, curly quotes, ellipsis — map Greek, sub/superscripts and common math symbols to LaTeX, and drop the rest (CJK, Arabic, Cyrillic). Probed 2026-11-12 over both caches: every title, name and venue compiles. JSON and BibTeX keep all Unicode.
- **No data, no file** (the faculty-profiles section contract): no ORCID on file, or a record with nothing for the section, exits 0 and writes nothing. A failed refetch uses the cached record, with a warning; with no cached record the section fails (exit 2). Under `--no-fetch` a mapped ORCID with no cache file also fails (exit 2, "run `just prefetch`"): a gap in the cache is not "no data".
- DOI links preserved and formatted as hyperlinks
- **BibTeX** (`run_bibtex.py`, `compose_cv.py --format bibtex`): an embedded ORCID citation typed `bibtex` is used only if it is a BibTeX entry (`@type{key,`, spaces allowed); HTML pages and formatted references typed `bibtex` get a generated entry instead. Every key is unique in the file, case-insensitively: a repeated or missing key becomes `Family` + year + the first free suffix (`a`, …, `z`, `aa`, …). Checked 2026-11-12 over the cache: one entry per publication, no repeated key (audit ORC-07).
- Period filtering via the shared flags `--year` (fiscal), `--acad_year`, `--cal_year`, `--semester` (see Options)
