# CLAUDE.md — academia-orcid

## Purpose

Data procurement from ORCID (owner, 2026-11-13): fetch and cache each faculty
member's ORCID record, and extract it into structured JSON, publications and
profile data, for the faculty composer (`../tamu-coe-faculty-profiles/`), which
renders it in every format (LaTeX vita, Word report). This repo renders nothing.
Institution-agnostic: a UIN → ORCID mapping database is the only local input.

**ORCID is the system of record.** Faculty maintain their ORCID profiles in
place of annual CVs, so every entry is what the faculty member put there; if one
is questioned, the answer is "this is what's in your ORCID record". The source
knowledge, and so the faithfulness, lives in extraction: DOIs, `self` vs
`part-of`, credit-name order, duplicate works. Source limits, not bugs: names
as publishers submitted them (often initials only), conference papers typed
`journal-article`, skeletal pre-2005 records, works without DOIs.

## Layout

```
academia-orcid/
├── run_json.py                 # the section entry point (JSON)
├── run_prefetch.py             # bulk cache fill (`just prefetch`)
├── src/academia_orcid/
│   ├── cli.py                  # run_json's plumbing: flags, UIN → ORCID, record load, exit codes
│   ├── fetch.py                # ORCID API client, ORCID_JSON/ cache, UIN → ORCID lookup
│   ├── prefetch.py             # bulk cache fill for every mapped ORCID
│   ├── extract.py              # record → publication entries and profile data
│   ├── json_export.py          # the JSON envelope (_meta, provenance)
│   └── config.py, logging_config.py, schema.py (ORCID v3.0 TypedDicts)
├── tests/
├── ORCID_JSON/                 # cached records (gitignored)
└── justfile                    # prefetch, test, lint, typecheck, format, check
```

## The entry point

```bash
python run_json.py --uin <uin> --mapping-db ../coe-data-db/en.db --output-dir <dir>   # publications
python run_json.py --orcid 0000-0002-2983-9884 --output-dir <dir> --section data
# + --fetch (default) | --no-fetch | --force-fetch
# → <dir>/orcid-publications.json or orcid-data.json; no file when there is nothing
```

- Exactly one of `--uin` (looked up in `--mapping-db`) and `--orcid`.
- **No period flag** (2026-11-13): every publication is written, with its `year`
  and `month`; the composer keeps the report period's.
- **Exit codes:** 0 done, with or without data; 1 bad input (a malformed id,
  given or in `faculty_identifiers`: a wrong id never passes for "no data", as in
  tamu-scholars; no `--mapping-db`; an en.db without `faculty_identifiers`, i.e.
  older than schema v17); 2 argparse errors, a fetch that failed with nothing
  cached, `--no-fetch` with nothing cached ("run `just prefetch`": a cache gap is
  not "no data"). A failed refetch uses the cached record, with a warning.
- **HTTP 404 is a failure here** (exit 2; prefetch `failed`), unlike tamu-scholars
  and academia-openalex, where it means "no such profile" and is remembered. ORCID
  iDs are persistent, so a 404 points at a wrong iD in the mapping rather than a
  profile that went away. None so far: all 453 mapped iDs are cached (2026-11-13).

## The JSON

**Publications:** `journal_articles`, `conference_papers`, `other_publications`
under `_meta` (`section`, `orcid_id`, `generated_at`, `total_count`, `provenance`).
Each entry: `raw_authors` (credit names as written), `author_names`
(`[{family, given}]`, every name), `title` (ORCID's markup kept: HTML tags,
`$…$` math; whitespace collapsed), `venue`, `year`, `month`, `doi`, `url`,
`pub_type`, `external_ids`, `citation`. The composer renders authors ("Family,
F.M.", "et al.") and markup per format.

**Provenance** (owner, 2026-11-13): `_meta.provenance` = `{source: "orcid", ids:
[orcid], curation: "author-curated", fetched_at: <cache time>}`, the same keys as
tamu-scholars and academia-openalex (`curation: "aggregated"`).

**Profile data:** `biography` (markup kept), `employment`, `education`,
`distinctions`, `memberships`, `external_service`, `fundings`,
`external_identifiers`, from the record's person and activities summaries.

## Extraction rules (publications)

- **Types:** journal articles `journal-article`, `journal-issue`, `article-journal`;
  conference papers `conference-paper`, `conference-abstract`, `conference-poster`,
  `paper-conference`; everything else other.
- **One entry per work:** ORCID groups works by shared identifiers only, so one
  work imported with and without a DOI lands in two groups. `collapse_duplicates`
  keeps one per same DOI (case-insensitive), or, when either lacks one, same type,
  title (20+ letters and digits) and year; the DOI-bearing copy wins, then journal
  over conference over other (owner, 2026-11-12).
- **DOIs** bare (`10.xxxx/...`; `normalize_doi`). Only the work's own DOI
  (relationship `self`, or none): a chapter whose only DOI is its book's (`part-of`)
  has none.
- **Names:** `split_name` reads "Given Family", "Family, Given" (56% of the cache)
  and trailing initials ("Doe J", "Smith John A").

## UIN → ORCID

en.db's `faculty_identifiers` (coe-data-core), Scheme `orcid`: the person's
lowest-Rank row, whitespace stripped (`IDENTIFIERS_TABLE` / `ORCID_SCHEME` in
`fetch.py`; this repo imports no coe-data-core). The cache is flat,
`ORCID_JSON/{orcid}.json`; academia-openalex reads it too.

## Bulk cache fill

`run_json.py` fetches on demand and treats a record older than the TTL (7 days)
as stale. `just prefetch` fills `ORCID_JSON/` ahead of time so the composer can run
`--no-fetch`. **This repo owns its cache:** faculty-profiles and academia-openalex
call this recipe rather than fetching themselves.

```bash
just prefetch                          # missing or stale records (en.db: $COE_DATA_DB or ../coe-data-db/en.db)
just prefetch --dry-run | --force
just prefetch --dept MEEN | --uin 123456789 | --uin-file nominees.txt   # union; repeatable
```

Records are written whole (temporary file renamed), so a stopped run resumes. A
work whose detail call fails keeps its summary (no contributors); the record is
`partial`, stale, and retried next run. Outcomes: `fetched`, `partial`, `fresh`,
`failed`, `invalid`; exit 1 if any failed or the mapping holds a malformed iD
(as tamu-scholars). About 6 works/s: ~290 ORCIDs in an hour.

## Shared code (with tamu-scholars and academia-openalex)

- **Hand-aligned copies** (owner, 2026-11-12; no drift test): `cli.py` (common flags,
  id lookup, `load_record`, exit codes; academia-openalex's
  `section_cli.py`), `fetch.py` (whole-file cache write, en.db lookup, partial
  records), `prefetch.py` (scope options, outcomes, exit code; not in
  academia-openalex), `config.py`, `logging_config.py`, and in `extract.py`
  `collapse_duplicates`. A change to one is
  checked against the others unless source-specific. Nothing is vendored from
  coe-data-core any more: the period and the rendering are the composer's.
- **The three as a group** (what is shared, what differs, curated vs aggregated):
  `../README.md`, "Publication sources".

## Development

`uv sync` (dev group: pytest, ruff, mypy; `requests` at runtime, PyYAML optional
for `.academia-orcid.yaml`). `just test`, `just lint`, `just typecheck`, `just
check`. Config (`.academia-orcid.yaml` in `./`, `~/` or `/etc/academia-orcid/`;
see the `.example`): API timeouts and rate limits, cache TTL and folder, JSON
indent; environment overrides `ORCID_API_BASE_URL`, `ORCID_CACHE_TTL`,
`ORCID_API_TIMEOUT`.

The LaTeX entry point, BibTeX export, DOI enrichment and standalone CV tool were
removed on 2026-11-13 (owner): nobody used the repo on its own, and the composer
renders the JSON. They are in git history.
