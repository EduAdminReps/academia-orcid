#!/usr/bin/env python3
"""Standalone ORCID CV Composer — generates complete CVs from ORCID data.

Produces LaTeX/PDF or DOCX documents using only public ORCID data, without
requiring the parent tamu-coe-faculty-profiles composer or privileged data.

Derived from tamu-coe-faculty-profiles/compose_latex.py and compose_docx.py.
See CLAUDE.md "Standalone CV Tool" section for upstream sync policy.

Usage:
    python tools/compose_cv.py --orcid 0000-0003-0831-6109
    python tools/compose_cv.py --orcid 0000-0003-0831-6109 --format docx
    python tools/compose_cv.py --orcid 0000-0003-0831-6109 --year 2020-2025
    python tools/compose_cv.py --orcid 0000-0003-0831-6109 --skip-compile
"""

import argparse
import logging
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# Ensure the package is importable (handles running from tools/ directory)
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from academia_orcid.config import get_config
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
    filter_publications_by_year,
    parse_year_filter,
)
from academia_orcid.fetch import (
    get_or_fetch_orcid_record,
    validate_orcid_id,
)
from academia_orcid.json_export import export_data, export_publications
from academia_orcid.latex import (
    escape_latex,
    generate_data_latex,
    generate_latex,
)
from academia_orcid.logging_config import setup_logging

logger = logging.getLogger("compose_cv")

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
DEFAULT_OUTPUT_BASE = _REPO_ROOT / "out_cv"


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

def generate_header(faculty_info: dict, template_path: Path, output_path: Path):
    """Generate header.tex from template with faculty info."""
    content = template_path.read_text()
    content = content.format(**faculty_info)
    output_path.write_text(content)


def generate_main(display_year: str, template_path: Path, output_path: Path):
    """Generate main.tex from template with report year."""
    content = template_path.read_text()
    content = content.format(report_year=display_year)
    output_path.write_text(content)


def cleanup_latex_byproducts(output_dir: Path):
    """Remove LaTeX compilation byproducts."""
    extensions = [".aux", ".log", ".out", ".toc", ".lof", ".lot",
                  ".fls", ".fdb_latexmk", ".synctex.gz"]
    for ext in extensions:
        for f in output_dir.glob(f"*{ext}"):
            try:
                f.unlink()
            except OSError:
                pass


def create_source_archive(output_dir: Path, report_id: str) -> Path:
    """Create a zip archive of source files."""
    # Clean byproducts and old PDFs/zips before archiving
    for ext in [".aux", ".log", ".out", ".toc", ".lof", ".lot",
                ".fls", ".fdb_latexmk", ".synctex.gz", ".pdf", ".zip"]:
        for f in output_dir.glob(f"*{ext}"):
            try:
                f.unlink()
            except OSError:
                pass

    zip_path = output_dir / f"{report_id}-source.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in output_dir.iterdir():
            if f.is_file() and f.suffix != ".zip":
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

def resolve_and_fetch(args) -> tuple[str, dict | None]:
    """Validate ORCID ID and fetch the record.

    Returns:
        Tuple of (orcid_id, record) or (orcid_id, None) on failure.
    """
    data_dir = Path(args.data_dir)
    orcid_id = args.orcid

    if not validate_orcid_id(orcid_id):
        logger.error(f"Invalid ORCID ID format: {orcid_id}")
        logger.error("ORCID IDs must match: XXXX-XXXX-XXXX-XXXX")
        return orcid_id, None

    logger.info(f"Using ORCID ID: {orcid_id}")

    fetch_enabled = not args.no_fetch
    force_fetch = args.force_fetch

    record = get_or_fetch_orcid_record(
        data_dir, orcid_id, fetch=fetch_enabled, force=force_fetch
    )
    if not record:
        logger.error(f"Could not load ORCID record for {orcid_id}")
        return orcid_id, None

    return orcid_id, record


# ---------------------------------------------------------------------------
# LaTeX pipeline
# ---------------------------------------------------------------------------

def generate_latex_cv(args):
    """Generate a complete ORCID CV as LaTeX source and PDF."""
    orcid_id, record = resolve_and_fetch(args)
    if not record:
        sys.exit(1)

    person = extract_person_info(record)
    logger.info(f"Faculty: {person['name']}")
    if person["institution"]:
        logger.info(f"Institution: {person['institution']}")
    if person["department"]:
        logger.info(f"Department: {person['department']}")

    # Year filter
    year_filter = parse_year_filter(args.year)
    if year_filter:
        display_year = f"{year_filter[0]}-{year_filter[1]}"
        logger.info(f"Year filter: {display_year}")
    else:
        display_year = "All Years"

    # Output directory
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_BASE / orcid_id

    if args.dry_run:
        logger.info(f"[dry-run] Would create: {output_dir}")
        logger.info(f"[dry-run] Would generate LaTeX CV for {person['name']}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

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
        (output_dir / "orcid-data.tex").write_text(data_latex)
        logger.info("  Created: orcid-data.tex")

    # Generate orcid-publications.tex
    logger.info("Generating publications section...")
    journal_articles, conference_papers, other_publications = extract_publications(record)

    if year_filter:
        journal_articles = filter_publications_by_year(journal_articles, year_filter)
        conference_papers = filter_publications_by_year(conference_papers, year_filter)
        other_publications = filter_publications_by_year(other_publications, year_filter)

    pubs_latex = generate_latex(orcid_id, journal_articles, conference_papers, other_publications)
    if pubs_latex:
        (output_dir / "orcid-publications.tex").write_text(pubs_latex)
        logger.info("  Created: orcid-publications.tex")

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
# DOCX pipeline
# ---------------------------------------------------------------------------

def generate_docx_cv(args):
    """Generate a complete ORCID CV as a Word document."""
    try:
        from tools.docx_formatter import OrcidDocxFormatter
    except ImportError:
        try:
            # Handle running from repo root vs tools/ directory
            from docx_formatter import OrcidDocxFormatter
        except ImportError:
            logger.error(
                "DOCX output requires python-docx. Install with: pip install python-docx"
            )
            sys.exit(1)

    orcid_id, record = resolve_and_fetch(args)
    if not record:
        sys.exit(1)

    person = extract_person_info(record)
    logger.info(f"Faculty: {person['name']}")

    # Year filter
    year_filter = parse_year_filter(args.year)
    if year_filter:
        year_display = f"{year_filter[0]}-{year_filter[1]}"
        logger.info(f"Year filter: {year_display}")
    else:
        year_display = None

    # Output directory
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_BASE / orcid_id

    if args.dry_run:
        logger.info(f"[dry-run] Would create: {output_dir}")
        logger.info(f"[dry-run] Would generate DOCX CV for {person['name']}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    # Extract all data
    biography = extract_biography(record)
    external_identifiers = extract_external_identifiers(record)
    fundings = extract_fundings(record)
    employments = extract_employments(record)
    educations = extract_educations(record)
    distinctions = extract_distinctions(record)
    memberships = extract_memberships(record)
    services = extract_services(record)

    journal_articles, conference_papers, other_publications = extract_publications(record)
    if year_filter:
        journal_articles = filter_publications_by_year(journal_articles, year_filter)
        conference_papers = filter_publications_by_year(conference_papers, year_filter)
        other_publications = filter_publications_by_year(other_publications, year_filter)

    # Build JSON data
    data_json = export_data(
        orcid_id, biography, external_identifiers, fundings,
        employments, educations, distinctions, memberships, services
    )
    pubs_json = export_publications(
        orcid_id, journal_articles, conference_papers, other_publications
    )

    # Assemble profile (matching composer's build_profile() structure)
    profile = {
        "_meta": {
            "uin": orcid_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "year_filter": year_display,
        },
        "identity": {
            "name": person["name"],
            "department_name": person["department"],
            "identifier_label": "ORCID",
            "identifier_value": orcid_id,
            "institution": person["institution"],
            "college": "",
        },
    }
    if data_json:
        profile["orcid_data"] = data_json
    if pubs_json:
        profile["orcid_publications"] = pubs_json

    # Format
    formatter = OrcidDocxFormatter()
    paths = formatter.format(profile, output_dir)
    for p in paths:
        logger.info(f"DOCX: {p}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate a standalone ORCID-based CV (LaTeX/PDF or DOCX)."
    )

    # Identification
    parser.add_argument("--orcid", required=True,
                        help="ORCID ID (e.g., 0000-0003-0831-6109)")

    # Format
    parser.add_argument(
        "--format", default="latex", choices=["latex", "docx"],
        help="Output format (default: latex)"
    )

    # Options
    parser.add_argument("--year", default=None,
                        help="Year filter for publications (YYYY-YYYY, YYYY, or 'all')")
    parser.add_argument("--output-dir", default=None,
                        help="Output directory (default: out_cv/<orcid-id>/)")
    parser.add_argument("--data-dir", default=str(_REPO_ROOT),
                        help="Base directory for ORCID cache (default: repo root)")

    # Fetch control
    parser.add_argument("--fetch", action="store_true", default=True,
                        help="Fetch from ORCID API if not cached (default)")
    parser.add_argument("--no-fetch", action="store_true",
                        help="Only use cached records")
    parser.add_argument("--force-fetch", action="store_true",
                        help="Always fetch from API (refresh cache)")

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

    return parser.parse_args()


def main():
    """Entry point."""
    args = parse_args()

    # Setup logging
    log_file = Path(args.log_file) if args.log_file else None
    setup_logging(level=args.log_level, log_file=log_file)

    if args.format == "latex":
        generate_latex_cv(args)
    elif args.format == "docx":
        generate_docx_cv(args)


if __name__ == "__main__":
    main()
