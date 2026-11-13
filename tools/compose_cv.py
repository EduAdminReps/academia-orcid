#!/usr/bin/env python3
"""Standalone ORCID CV Composer — generates complete CVs from ORCID data.

Produces a LaTeX/PDF CV or a BibTeX file using only public ORCID data, without
requiring the parent tamu-coe-faculty-profiles composer or privileged data.

Adapted from tamu-coe-faculty-profiles/compose_latex.py (templates, compilation,
archiving); maintained here, not synced (see CLAUDE.md "Standalone CV Tool").

Usage:
    python tools/compose_cv.py --orcid 0000-0003-0831-6109
    python tools/compose_cv.py --orcid 0000-0003-0831-6109 --cal_year 2020-2025
    python tools/compose_cv.py --orcid 0000-0003-0831-6109 --skip-compile
    python tools/compose_cv.py --orcid 0000-0003-0831-6109 --format bibtex

Exit codes: 0 done; 1 bad input or failed compilation; 2 the ORCID record could
not be fetched and none is cached (or, under --no-fetch, none is cached).
"""

import argparse
import logging
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

# Ensure the package is importable (handles running from tools/ directory)
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from academia_orcid import (
    OUTPUT_DATA_TEX,
    OUTPUT_PUBLICATIONS_SUMMARY_TEX,
    OUTPUT_PUBLICATIONS_TEX,
)
from academia_orcid.cli import resolve_period
from academia_orcid.extract import (
    extract_biography,
    extract_distinctions,
    extract_educations,
    extract_employments,
    extract_external_identifiers,
    extract_fundings,
    extract_memberships,
    extract_publications,
    extract_services,
    filter_publications_by_period,
)
from academia_orcid.fetch import (
    OrcidFetchError,
    get_or_fetch_orcid_record,
    validate_orcid_id,
)
from academia_orcid.latex import (
    escape_latex,
    generate_data_latex,
    generate_latex,
    generate_latex_summary,
)
from academia_orcid.logging_config import setup_logging
from academia_orcid.periods import add_period_args

# Under the academia_orcid logger tree, which setup_logging configures (ORC-15).
logger = logging.getLogger("academia_orcid.compose_cv")

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
DEFAULT_OUTPUT_BASE = _REPO_ROOT / "out_cv"


def _maybe_enrich(args, journal_articles, conference_papers, other_publications):
    """Apply DOI enrichment if --enrich flag is set. Returns the (possibly enriched) lists."""
    if args.enrich:
        from academia_orcid.enrich import enrich_publications
        logger.info("Enriching publications via DOI content negotiation...")
        journal_articles = enrich_publications(journal_articles)
        conference_papers = enrich_publications(conference_papers)
        other_publications = enrich_publications(other_publications)
    return journal_articles, conference_papers, other_publications


# ---------------------------------------------------------------------------
# Person info extraction from ORCID record
# ---------------------------------------------------------------------------

def extract_person_info(record: dict) -> dict:
    """Extract name, institution, and department from an ORCID record.

    Reuses the already-fetched full record rather than making separate
    API calls (more efficient than the parent composer's get_orcid_info()).

    Returns:
        Dict with keys: name, institution, department
    """
    # Name from person/name
    person = record.get("person", {})
    name_obj = person.get("name", {})
    if name_obj:
        given = (name_obj.get("given-names") or {}).get("value", "")
        family = (name_obj.get("family-name") or {}).get("value", "")
        name = f"{given} {family}".strip() or "Unknown"
    else:
        name = "Unknown"

    # Institution and department from current employment
    employments = extract_employments(record)
    institution = ""
    department = ""
    if employments:
        # Prefer current employment (no end_year), otherwise most recent
        current = [e for e in employments if not e.get("end_year")]
        best = current[0] if current else employments[0]
        institution = best.get("organization", "")
        department = best.get("department", "")

    return {
        "name": name,
        "institution": institution,
        "department": department,
    }


# ---------------------------------------------------------------------------
# LaTeX utilities (adapted from compose_latex.py)
# ---------------------------------------------------------------------------

def _substitute_template(content: str, variables: dict) -> str:
    """Substitute %%key%% placeholders in a template string.

    Uses %%key%% delimiters to avoid conflicts with LaTeX braces.
    """
    for key, value in variables.items():
        content = content.replace(f"%%{key}%%", str(value))
    return content


def generate_header(faculty_info: dict, template_path: Path, output_path: Path):
    """Generate header.tex from template with faculty info."""
    content = template_path.read_text()
    content = _substitute_template(content, faculty_info)
    # Remove lines where an optional field was empty, e.g. {\Large }\\[1.5em].
    # LaTeX raises "There's no line here to end" when \\ follows an empty group
    # in a center environment. This happens when college/department are absent.
    content = re.sub(r'[ \t]*\{\\[A-Za-z]+[ \t]*\}\\\\[^\n]*\n', '', content)
    output_path.write_text(content)


def generate_main(display_year: str, template_path: Path, output_path: Path):
    """Generate main.tex from template with report year."""
    content = template_path.read_text()
    content = _substitute_template(content, {"report_year": display_year})
    output_path.write_text(content)


# What one LaTeX run writes into the output directory. Only these are removed
# or archived: --output-dir may be a folder holding other files (audit ORC-08).
LATEX_SOURCES = ["preamble.tex", "header.tex", "main.tex"]
FRAGMENTS = [OUTPUT_DATA_TEX, OUTPUT_PUBLICATIONS_TEX, OUTPUT_PUBLICATIONS_SUMMARY_TEX]
LATEX_BYPRODUCTS = [".aux", ".log", ".out", ".toc", ".lof", ".lot",
                    ".fls", ".fdb_latexmk", ".synctex.gz"]


def _unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def cleanup_latex_byproducts(output_dir: Path):
    """Remove main.tex's compilation byproducts (main.aux, main.log, ...)."""
    for ext in LATEX_BYPRODUCTS:
        _unlink(output_dir / f"main{ext}")


def remove_stale_outputs(output_dir: Path, report_id: str):
    """Remove an earlier run's fragments, PDF and archive (and nothing else).

    A fragment is written only when it has data, so one left from an earlier run
    would otherwise be compiled into this run's CV (audit ORC-08).
    """
    for name in FRAGMENTS:
        _unlink(output_dir / name)
    for name in (f"{report_id}-cv.pdf", f"{report_id}-source.zip", "main.pdf"):
        _unlink(output_dir / name)
    cleanup_latex_byproducts(output_dir)


def create_source_archive(output_dir: Path, report_id: str) -> Path:
    """Zip this run's LaTeX sources (templates and the fragments written)."""
    zip_path = output_dir / f"{report_id}-source.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in LATEX_SOURCES + FRAGMENTS:
            f = output_dir / name
            if f.is_file():
                zf.write(f, f.name)
    return zip_path


def compile_latex(output_dir: Path, report_id: str) -> Path | None:
    """Compile LaTeX document to PDF (runs pdflatex twice for TOC)."""
    try:
        for _ in range(2):
            result = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", "main.tex"],
                cwd=output_dir,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                logger.warning("pdflatex returned non-zero exit code")
                logger.debug(result.stdout[-2000:] if result.stdout else "")

        pdf_path = output_dir / "main.pdf"
        if pdf_path.exists():
            final_path = output_dir / f"{report_id}-cv.pdf"
            shutil.move(pdf_path, final_path)
            cleanup_latex_byproducts(output_dir)
            return final_path
        return None
    except FileNotFoundError:
        logger.error("pdflatex not found. Install TeX Live or MacTeX.")
        return None


# ---------------------------------------------------------------------------
# Shared: resolve ORCID ID and fetch record
# ---------------------------------------------------------------------------

def resolve_and_fetch(args) -> tuple[str, dict]:
    """Validate the ORCID ID and load its record (cached or fetched).

    Exits 1 on a malformed ID, and 2 when no record can be had: the fetch failed
    with nothing cached, or --no-fetch and nothing cached (ORC-15).
    """
    data_dir = Path(args.data_dir)
    orcid_id = args.orcid

    if not validate_orcid_id(orcid_id):
        logger.error(f"Invalid ORCID ID format: {orcid_id}")
        logger.error("ORCID IDs must match: XXXX-XXXX-XXXX-XXXX")
        sys.exit(1)

    logger.info(f"Using ORCID ID: {orcid_id}")

    try:
        record = get_or_fetch_orcid_record(
            data_dir, orcid_id, fetch=args.fetch, force=args.force_fetch
        )
    except OrcidFetchError as e:
        logger.error(f"ORCID API fetch failed for {orcid_id}: {e}")
        sys.exit(2)
    if not record:
        hint = " (not cached; drop --no-fetch)" if not args.fetch else ""
        logger.error(f"Could not load ORCID record for {orcid_id}{hint}")
        sys.exit(2)

    return orcid_id, record


# ---------------------------------------------------------------------------
# LaTeX pipeline
# ---------------------------------------------------------------------------

def generate_latex_cv(args):
    """Generate a complete ORCID CV as LaTeX source and PDF."""
    orcid_id, record = resolve_and_fetch(args)

    person = extract_person_info(record)
    logger.info(f"Faculty: {person['name']}")
    if person["institution"]:
        logger.info(f"Institution: {person['institution']}")
    if person["department"]:
        logger.info(f"Department: {person['department']}")

    # Report period (publications only)
    period = resolve_period(args)
    display_year = period.label()
    if not period.is_all:
        logger.info(f"Period: {display_year}")

    # Output directory
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_BASE / orcid_id

    if args.dry_run:
        logger.info(f"[dry-run] Would create: {output_dir}")
        logger.info(f"[dry-run] Would generate LaTeX CV for {person['name']}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    remove_stale_outputs(output_dir, orcid_id)

    # Copy preamble
    preamble_src = TEMPLATES_DIR / "preamble.tex"
    shutil.copy(preamble_src, output_dir / "preamble.tex")

    # Generate header.tex
    faculty_info = {
        "name": escape_latex(person["name"]),
        "department": "",
        "department_name": escape_latex(person["department"]),
        "title": "",
        "identifier_label": "ORCID",
        "identifier_value": orcid_id,
        "institution": escape_latex(person["institution"]),
        "college": "",
    }
    generate_header(faculty_info, TEMPLATES_DIR / "header.tex.template",
                    output_dir / "header.tex")

    # Generate orcid-data.tex
    logger.info("Generating ORCID data section...")
    biography = extract_biography(record)
    external_identifiers = extract_external_identifiers(record)
    fundings = extract_fundings(record)
    employments = extract_employments(record)
    educations = extract_educations(record)
    distinctions = extract_distinctions(record)
    memberships = extract_memberships(record)
    services = extract_services(record)

    data_latex = generate_data_latex(
        orcid_id, biography, external_identifiers, fundings,
        employments, educations, distinctions, memberships, services
    )
    if data_latex:
        (output_dir / OUTPUT_DATA_TEX).write_text(data_latex)
        logger.info(f"  Created: {OUTPUT_DATA_TEX}")

    # Generate orcid-publications.tex
    logger.info("Generating publications section...")
    journal_articles, conference_papers, other_publications = extract_publications(record)

    journal_articles = filter_publications_by_period(journal_articles, period)
    conference_papers = filter_publications_by_period(conference_papers, period)
    other_publications = filter_publications_by_period(other_publications, period)

    # Optional DOI enrichment
    journal_articles, conference_papers, other_publications = _maybe_enrich(
        args, journal_articles, conference_papers, other_publications
    )

    pubs_latex = generate_latex(orcid_id, journal_articles, conference_papers, other_publications)
    if pubs_latex:
        (output_dir / OUTPUT_PUBLICATIONS_TEX).write_text(pubs_latex)
        (output_dir / OUTPUT_PUBLICATIONS_SUMMARY_TEX).write_text(
            generate_latex_summary(orcid_id, journal_articles, conference_papers, other_publications)
        )
        logger.info(f"  Created: {OUTPUT_PUBLICATIONS_TEX}, {OUTPUT_PUBLICATIONS_SUMMARY_TEX}")

    # Generate main.tex
    generate_main(display_year, TEMPLATES_DIR / "main.tex.template",
                  output_dir / "main.tex")

    # Source archive
    logger.info("Creating source archive...")
    zip_path = create_source_archive(output_dir, orcid_id)
    logger.info(f"  Created: {zip_path.name}")

    # Compile
    if args.skip_compile:
        logger.info("Skipping LaTeX compilation (--skip-compile)")
        logger.info(f"Output directory: {output_dir}")
        return

    logger.info("Compiling LaTeX...")
    pdf_path = compile_latex(output_dir, orcid_id)
    if pdf_path:
        logger.info(f"PDF: {pdf_path}")
    else:
        logger.error("LaTeX compilation failed")
        sys.exit(1)


# ---------------------------------------------------------------------------
# BibTeX pipeline
# ---------------------------------------------------------------------------

def generate_bibtex_cv(args):
    """Generate a BibTeX file from ORCID publications."""
    from academia_orcid.bibtex_export import export_bibtex

    orcid_id, record = resolve_and_fetch(args)

    person = extract_person_info(record)
    logger.info(f"Faculty: {person['name']}")

    # Report period
    period = resolve_period(args)
    if not period.is_all:
        logger.info(f"Period: {period.label()}")

    # Output directory
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_BASE / orcid_id

    if args.dry_run:
        logger.info(f"[dry-run] Would create: {output_dir}")
        logger.info(f"[dry-run] Would generate BibTeX for {person['name']}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    bib_path = output_dir / f"{orcid_id}.bib"
    _unlink(bib_path)  # an earlier run's file must not pass for this period's

    # Extract publications
    journal_articles, conference_papers, other_publications = extract_publications(record)

    journal_articles = filter_publications_by_period(journal_articles, period)
    conference_papers = filter_publications_by_period(conference_papers, period)
    other_publications = filter_publications_by_period(other_publications, period)

    # Optional DOI enrichment
    journal_articles, conference_papers, other_publications = _maybe_enrich(
        args, journal_articles, conference_papers, other_publications
    )

    # Generate BibTeX
    bibtex_content = export_bibtex(
        orcid_id, journal_articles, conference_papers, other_publications
    )

    if not bibtex_content:
        logger.info("No publications found; skipping .bib file creation.")
        return

    bib_path.write_text(bibtex_content, encoding="utf-8")
    logger.info(f"BibTeX: {bib_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None):
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate a standalone ORCID-based CV (LaTeX/PDF or BibTeX)."
    )

    # Identification
    parser.add_argument("--orcid", required=True,
                        help="ORCID ID (e.g., 0000-0003-0831-6109)")

    # Format
    parser.add_argument(
        "--format", default="latex", choices=["latex", "bibtex"],
        help="Output format (default: latex)"
    )

    # Options
    add_period_args(parser)  # filters publications; see academia_orcid.periods
    parser.add_argument("--output-dir", default=None,
                        help="Output directory (default: out_cv/<orcid-id>/)")
    parser.add_argument("--data-dir", default=str(_REPO_ROOT),
                        help="Base directory for ORCID cache (default: repo root)")

    # Fetch control
    fetch_group = parser.add_mutually_exclusive_group()
    fetch_group.add_argument("--fetch", dest="fetch", action="store_true", default=True,
                             help="Fetch from ORCID API if not cached (default)")
    fetch_group.add_argument("--no-fetch", dest="fetch", action="store_false",
                             help="Only use cached records")
    fetch_group.add_argument("--force-fetch", action="store_true",
                             help="Always fetch from API (refresh cache)")

    # Enrichment
    parser.add_argument("--enrich", action="store_true",
                        help="Enrich publications via DOI content negotiation (fills gaps)")

    # LaTeX-specific
    parser.add_argument("--skip-compile", action="store_true",
                        help="Generate LaTeX source but skip PDF compilation")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without making changes")

    # Logging
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                        help="Logging level (default: INFO)")
    parser.add_argument("--log-file", default=None,
                        help="Log to file instead of stderr")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None):
    """Entry point."""
    args = parse_args(argv)

    # Setup logging
    log_file = Path(args.log_file) if args.log_file else None
    setup_logging(level=args.log_level, log_file=log_file)

    if args.format == "latex":
        generate_latex_cv(args)
    elif args.format == "bibtex":
        generate_bibtex_cv(args)


if __name__ == "__main__":
    main()
