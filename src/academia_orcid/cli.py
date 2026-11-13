"""Command-line interface for generating ORCID LaTeX sections."""

import argparse
import logging
import re
import sys
from pathlib import Path

from academia_orcid import (
    OUTPUT_DATA_TEX,
    OUTPUT_PUBLICATIONS_TEX,
    SECTION_DATA,
    SECTION_PUBLICATIONS,
    VALID_SECTIONS,
)
from academia_orcid.config import get_config
from academia_orcid.logging_config import setup_logging
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
from academia_orcid.latex import generate_data_latex, generate_latex
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


def main():
    """Generate faculty sections from ORCID data."""
    parser = argparse.ArgumentParser(
        description="Generate faculty sections from ORCID data for vita report."
    )
    parser.add_argument("--uin", default=None, help="Faculty UIN (required unless --orcid is provided)")
    parser.add_argument("--orcid", default=None, help="ORCID ID directly (bypasses UIN→ORCID mapping)")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--data-dir", default=".", help="Base directory containing ORCID data")
    parser.add_argument(
        "--section",
        default=SECTION_PUBLICATIONS,
        choices=VALID_SECTIONS,
        help="Section to generate: publications or data"
    )
    add_period_args(parser)  # publications only; ignored for --section data
    fetch_group = parser.add_mutually_exclusive_group()
    fetch_group.add_argument(
        "--fetch",
        dest="fetch",
        action="store_true",
        default=True,
        help="Fetch ORCID record from API if not in cache (default)"
    )
    fetch_group.add_argument(
        "--no-fetch",
        dest="fetch",
        action="store_false",
        help="Do not fetch from API, only use cached records"
    )
    fetch_group.add_argument(
        "--force-fetch",
        action="store_true",
        help="Always fetch from API, even if cached record exists (refreshes cache)"
    )
    parser.add_argument(
        "--mapping-db",
        default=None,
        help="Path to SQLite database (en.db) with the faculty_identifiers table (required when using --uin)"
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to YAML configuration file (optional, defaults to .academia-orcid.yaml)"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)"
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Optional log file path (logs to stderr if not specified)"
    )

    args = parser.parse_args()

    # Setup logging
    log_file = Path(args.log_file) if args.log_file else None
    setup_logging(level=args.log_level, log_file=log_file)
    logger = logging.getLogger("academia_orcid.cli")

    # Load configuration (if specified via --config, or from default locations)
    config_file = Path(args.config) if args.config else None
    config = get_config(config_file)
    logger.debug(f"Using configuration (cache TTL: {config.cache_ttl}s, API timeout: {config.api_timeout}s)")

    # Validate: need either --uin or --orcid
    if not args.uin and not args.orcid:
        parser.error("Either --uin or --orcid is required")

    # Handle fetch flags
    fetch_enabled = args.fetch
    force_fetch = args.force_fetch

    data_path = Path(args.data_dir)
    output_path = Path(args.output_dir)
    section = args.section
    period = resolve_period(args)

    # Log period status
    if not period.is_all and section == SECTION_DATA:
        logger.info("Note: the period is ignored for --section data (all data included)")
    elif not period.is_all:
        logger.info(f"Period: {period.label()}")

    # Determine output file based on section type
    if section == SECTION_PUBLICATIONS:
        output_filename = OUTPUT_PUBLICATIONS_TEX
    else:
        output_filename = OUTPUT_DATA_TEX

    # Resolve ORCID ID: either directly provided or looked up from UIN
    if args.orcid:
        # Direct ORCID ID provided — skip UIN mapping
        orcid_id = args.orcid

        # Validate ORCID ID format
        if not validate_orcid_id(orcid_id):
            logger.error(f"Invalid ORCID ID format: {orcid_id}")
            logger.error("ORCID IDs must match the pattern: XXXX-XXXX-XXXX-XXXX")
            sys.exit(1)

        dept = None
        logger.info(f"Using ORCID ID directly: {orcid_id}")
    else:
        # UIN provided — look up ORCID ID from mapping database
        uin = args.uin

        # Validate UIN format
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

        orcid_id = get_orcid_for_uin(db_path, uin)
        dept = None

        if not orcid_id:
            # No data for this section: no file (section contract rule 5; audit ORC-04).
            logger.info(f"No ORCID ID on file for UIN {uin}; no {section} section.")
            return

        logger.info(f"Found ORCID {orcid_id} for UIN {uin}")

    # Load ORCID record from cache, or fetch from API if not cached. A failed
    # refetch falls back to a cached record (get_or_fetch_orcid_record); with none,
    # the section fails (exit 2) and writes nothing (audit ORC-04).
    try:
        record = get_or_fetch_orcid_record(data_path, orcid_id, dept, fetch=fetch_enabled, force=force_fetch)
    except OrcidFetchError as e:
        logger.error(f"ORCID API fetch failed for {orcid_id}: {e}")
        sys.exit(2)
    if not record:
        if not fetch_enabled:
            # Under --no-fetch, a missing record is a gap in the cache, not "no data".
            logger.error(f"ORCID record for {orcid_id} is not cached; run `just prefetch`.")
            sys.exit(2)
        logger.info(f"No ORCID record for {orcid_id}; no {section} section.")
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
    print(str(section_file))
