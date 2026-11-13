"""Command-line interface for generating ORCID LaTeX sections.

Also the plumbing the three entry points share (run_latex.py, run_json.py,
run_bibtex.py): the common flags, the UIN → ORCID lookup and the record load,
with one set of exit codes:

- 0: done, with or without data (no data writes no file; section contract rule 5)
- 1: bad input (malformed --uin/--orcid/period, no --mapping-db, an en.db
  without ``faculty_identifiers``)
- 2: argparse errors; the ORCID API failed with nothing cached; under
  ``--no-fetch`` a mapped ORCID with no cache file
"""

import argparse
import logging
import re
import sqlite3
import sys
from pathlib import Path

from academia_orcid import (
    OUTPUT_DATA_TEX,
    OUTPUT_PUBLICATIONS_SUMMARY_TEX,
    OUTPUT_PUBLICATIONS_TEX,
    SECTION_DATA,
    SECTION_PUBLICATIONS,
    VALID_SECTIONS,
)
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
    filter_publications_by_period,
)
from academia_orcid.fetch import (
    OrcidFetchError,
    get_or_fetch_orcid_record,
    get_orcid_for_uin,
    validate_orcid_id,
)
from academia_orcid.latex import generate_data_latex, generate_latex, generate_latex_summary
from academia_orcid.logging_config import setup_logging
from academia_orcid.periods import Period, add_period_args, period_from_args


def validate_uin(uin: str) -> bool:
    """Validate UIN format.

    UINs must be exactly 9 digits.

    Args:
        uin: The UIN to validate

    Returns:
        True if valid format, False otherwise
    """
    if not uin or not isinstance(uin, str):
        return False
    return bool(re.match(r'^\d{9}$', uin))


def resolve_period(args: argparse.Namespace) -> Period:
    """The report period from --year / --acad_year / --cal_year / --semester.

    Same meaning in every COE repo (``academia_orcid.periods``); no flag means
    all years. Exits 1 with a message on a malformed value (fail fast).
    """
    try:
        return period_from_args(args)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """The flags every section entry point takes (run_latex, run_json, run_bibtex)."""
    who = parser.add_mutually_exclusive_group(required=True)
    who.add_argument("--uin", help="Faculty UIN (looked up in --mapping-db)")
    who.add_argument("--orcid", help="ORCID ID directly (bypasses the UIN→ORCID mapping)")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--data-dir", default=".", help="Base directory containing ORCID_JSON/")
    add_period_args(parser)  # publications only; ignored for --section data
    fetch_group = parser.add_mutually_exclusive_group()
    fetch_group.add_argument(
        "--fetch", dest="fetch", action="store_true", default=True,
        help="Fetch ORCID record from API if not in cache (default)",
    )
    fetch_group.add_argument(
        "--no-fetch", dest="fetch", action="store_false",
        help="Do not fetch from API, only use cached records",
    )
    fetch_group.add_argument(
        "--force-fetch", action="store_true",
        help="Always fetch from API, even if cached record exists (refreshes cache)",
    )
    parser.add_argument(
        "--mapping-db", default=None,
        help="Path to SQLite database (en.db) with the faculty_identifiers table (required with --uin)",
    )
    parser.add_argument(
        "--config", default=None,
        help="Path to YAML configuration file (optional, defaults to .academia-orcid.yaml)",
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--log-file", default=None,
        help="Optional log file path (logs to stderr if not specified)",
    )


def setup_from_args(args: argparse.Namespace, logger_name: str) -> logging.Logger:
    """Logging and configuration from the common flags; returns the entry point's logger."""
    setup_logging(level=args.log_level, log_file=Path(args.log_file) if args.log_file else None)
    logger = logging.getLogger(logger_name)
    config = get_config(Path(args.config) if args.config else None)
    logger.debug(f"Using configuration (cache TTL: {config.cache_ttl}s, API timeout: {config.api_timeout}s)")
    return logger


def resolve_orcid_id(args: argparse.Namespace, logger: logging.Logger) -> str | None:
    """The ORCID iD to report on, from --orcid or from --uin via en.db.

    Returns None when the UIN has no ORCID iD (no data: the caller writes no
    file and exits 0). Exits 1 on a malformed id, a missing --mapping-db, or an
    en.db without the ``faculty_identifiers`` table.
    """
    if args.orcid:
        if not validate_orcid_id(args.orcid):
            logger.error(f"Invalid ORCID ID format: {args.orcid}")
            logger.error("ORCID IDs must match the pattern: XXXX-XXXX-XXXX-XXXX")
            sys.exit(1)
        logger.info(f"Using ORCID ID directly: {args.orcid}")
        return args.orcid

    uin = args.uin
    if not validate_uin(uin):
        logger.error(f"Invalid UIN format: {uin}")
        logger.error("UINs must be exactly 9 digits")
        sys.exit(1)
    if not args.mapping_db:
        logger.error("--mapping-db is required when using --uin")
        sys.exit(1)
    db_path = Path(args.mapping_db)
    if not db_path.exists():
        logger.error(f"Mapping database not found: {db_path}")
        sys.exit(1)

    try:
        orcid_id = get_orcid_for_uin(db_path, uin)
    except sqlite3.Error as e:
        logger.error(
            f"Cannot read faculty_identifiers from {db_path} ({e}); "
            "en.db schema v17 or later is needed (rebuild it with coe-data-core)"
        )
        sys.exit(1)
    if not orcid_id:
        logger.info(f"No ORCID ID on file for UIN {uin}.")
        return None
    logger.info(f"Found ORCID {orcid_id} for UIN {uin}")
    return orcid_id


def load_record(args: argparse.Namespace, orcid_id: str, logger: logging.Logger) -> dict | None:
    """The ORCID record, cached or fetched as the fetch flags say.

    A failed refetch falls back to a cached record (get_or_fetch_orcid_record).
    Exits 2 when the fetch fails with nothing cached, and under --no-fetch when
    the record is not cached (a gap in the cache is not "no data"). Returns None
    only when a fetch returned no record.
    """
    try:
        record = get_or_fetch_orcid_record(
            Path(args.data_dir), orcid_id, fetch=args.fetch, force=args.force_fetch
        )
    except OrcidFetchError as e:
        logger.error(f"ORCID API fetch failed for {orcid_id}: {e}")
        sys.exit(2)
    if not record:
        if not args.fetch:
            logger.error(f"ORCID record for {orcid_id} is not cached; run `just prefetch`.")
            sys.exit(2)
        logger.info(f"No ORCID record for {orcid_id}.")
        return None
    return record


def main(argv: list[str] | None = None):
    """Generate faculty sections from ORCID data."""
    parser = argparse.ArgumentParser(
        description="Generate faculty sections from ORCID data for vita report."
    )
    add_common_args(parser)
    parser.add_argument(
        "--section",
        default=SECTION_PUBLICATIONS,
        choices=VALID_SECTIONS,
        help="Section to generate: publications or data"
    )
    args = parser.parse_args(argv)
    logger = setup_from_args(args, "academia_orcid.cli")

    output_path = Path(args.output_dir)
    section = args.section
    period = resolve_period(args)

    # Log period status
    if not period.is_all and section == SECTION_DATA:
        logger.info("Note: the period is ignored for --section data (all data included)")
    elif not period.is_all:
        logger.info(f"Period: {period.label()}")

    output_filename = OUTPUT_PUBLICATIONS_TEX if section == SECTION_PUBLICATIONS else OUTPUT_DATA_TEX

    # An earlier run's summary must not outlive its publications file: the composer
    # template inputs it whenever it exists.
    if section == SECTION_PUBLICATIONS:
        (output_path / OUTPUT_PUBLICATIONS_SUMMARY_TEX).unlink(missing_ok=True)

    orcid_id = resolve_orcid_id(args, logger)
    if orcid_id is None:
        # No data for this section: no file (section contract rule 5; audit ORC-04).
        logger.info(f"No {section} section.")
        return
    record = load_record(args, orcid_id, logger)
    if record is None:
        logger.info(f"No {section} section.")
        return

    if section == SECTION_PUBLICATIONS:
        # Extract publications
        journal_articles, conference_papers, other_publications = extract_publications(record)
        total_before = len(journal_articles) + len(conference_papers) + len(other_publications)

        # Keep publications overlapping the period
        if not period.is_all:
            journal_articles = filter_publications_by_period(journal_articles, period)
            conference_papers = filter_publications_by_period(conference_papers, period)
            other_publications = filter_publications_by_period(other_publications, period)
            total_after = len(journal_articles) + len(conference_papers) + len(other_publications)
            logger.info(f"Found {total_before} publications, {total_after} in {period.label()}")
        else:
            logger.info(f"Found {len(journal_articles)} journal articles, {len(conference_papers)} conference papers, {len(other_publications)} other")

        # Generate LaTeX
        latex = generate_latex(orcid_id, journal_articles, conference_papers, other_publications)
    else:
        # Extract ORCID data fields
        biography = extract_biography(record)
        external_identifiers = extract_external_identifiers(record)
        fundings = extract_fundings(record)
        employments = extract_employments(record)
        educations = extract_educations(record)
        distinctions = extract_distinctions(record)
        memberships = extract_memberships(record)
        services = extract_services(record)

        logger.info(f"Found: {len(external_identifiers)} external IDs, {len(fundings)} fundings, "
                    f"{len(employments)} employments, {len(educations)} educations, "
                    f"{len(distinctions)} distinctions, {len(memberships)} memberships, "
                    f"{len(services)} services")

        # Generate LaTeX
        latex = generate_data_latex(
            orcid_id, biography, external_identifiers, fundings,
            employments, educations, distinctions, memberships, services
        )

    # Don't write file if no data (composer uses file existence to decide inclusion)
    if not latex:
        logger.info(f"No {section} data found; skipping file creation.")
        return

    # Write output
    output_path.mkdir(parents=True, exist_ok=True)
    section_file = output_path / output_filename
    section_file.write_text(latex)
    logger.info(f"Generated: {section_file}")

    # The summary (profile link, counts) goes under the template's own heading.
    if section == SECTION_PUBLICATIONS:
        summary_file = output_path / OUTPUT_PUBLICATIONS_SUMMARY_TEX
        summary_file.write_text(
            generate_latex_summary(orcid_id, journal_articles, conference_papers, other_publications)
        )
        logger.info(f"Generated: {summary_file}")

    print(str(section_file))
