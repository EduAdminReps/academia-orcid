#!/usr/bin/env python3
"""CLI entry point for ORCID JSON export.

Parallel to run_latex.py (LaTeX), this outputs structured JSON for the
agentic pipeline. Same CLI contract: --uin, --output-dir, --section, --year.

Output:
    {output-dir}/orcid-data.json         (--section data)
    {output-dir}/orcid-publications.json (--section publications)
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from academia_orcid import SECTION_DATA, SECTION_PUBLICATIONS, VALID_SECTIONS
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
    filter_publications_by_year,
    parse_year_filter,
)
from academia_orcid.cli import validate_uin
from academia_orcid.fetch import OrcidFetchError, get_or_fetch_orcid_record, get_orcid_for_uin, validate_orcid_id
from academia_orcid.json_export import export_data, export_publications


def main():
    """Generate ORCID JSON export for a faculty member."""
    parser = argparse.ArgumentParser(
        description="Export ORCID data as structured JSON for agentic pipeline."
    )
    parser.add_argument("--uin", default=None, help="Faculty UIN")
    parser.add_argument("--orcid", default=None, help="ORCID ID directly")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--data-dir", default=".", help="Base directory for ORCID cache")
    parser.add_argument(
        "--section",
        default=SECTION_PUBLICATIONS,
        choices=VALID_SECTIONS,
        help="Section to export: publications or data",
    )
    parser.add_argument(
        "--year", default=None,
        help="Year filter (YYYY-YYYY, YYYY, or 'all'). Ignored for --section data.",
    )
    parser.add_argument("--fetch", action="store_true", default=True)
    parser.add_argument("--no-fetch", action="store_true")
    parser.add_argument("--force-fetch", action="store_true")
    parser.add_argument("--mapping-db", default=None, help="Path to SQLite with orcid_mapping")
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
    logger = logging.getLogger("academia_orcid.run_json")

    # Load configuration (if specified via --config, or from default locations)
    config_file = Path(args.config) if args.config else None
    config = get_config(config_file)

    if not args.uin and not args.orcid:
        parser.error("Either --uin or --orcid is required")

    fetch_enabled = args.fetch and not args.no_fetch
    force_fetch = args.force_fetch
    data_path = Path(args.data_dir)
    output_path = Path(args.output_dir)
    section = args.section
    year_filter = parse_year_filter(args.year) if section == SECTION_PUBLICATIONS else None

    # Determine output filename
    if section == SECTION_PUBLICATIONS:
        output_filename = "orcid-publications.json"
    else:
        output_filename = "orcid-data.json"

    # Resolve ORCID ID
    if args.orcid:
        orcid_id = args.orcid

        # Validate ORCID ID format
        if not validate_orcid_id(orcid_id):
            logger.error(f"Invalid ORCID ID format: {orcid_id}")
            logger.error("ORCID IDs must match the pattern: XXXX-XXXX-XXXX-XXXX")
            sys.exit(1)

        logger.info(f"Using ORCID ID directly: {orcid_id}")
    else:
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
        if not orcid_id:
            logger.warning(f"No ORCID ID found for UIN {uin}; skipping.")
            return

        logger.info(f"Found ORCID {orcid_id} for UIN {uin}")

    # Load ORCID record
    try:
        record = get_or_fetch_orcid_record(data_path, orcid_id, None, fetch=fetch_enabled, force=force_fetch)
    except OrcidFetchError as e:
        logger.error(f"ORCID API fetch failed for {orcid_id}: {e}")
        sys.exit(2)
    if not record:
        logger.warning(f"No ORCID record found for {orcid_id}; skipping.")
        return

    # Extract and export
    if section == SECTION_PUBLICATIONS:
        journal_articles, conference_papers, other_publications = extract_publications(record)

        if year_filter:
            journal_articles = filter_publications_by_year(journal_articles, year_filter)
            conference_papers = filter_publications_by_year(conference_papers, year_filter)
            other_publications = filter_publications_by_year(other_publications, year_filter)

        data = export_publications(orcid_id, journal_articles, conference_papers, other_publications)
    else:
        data = export_data(
            orcid_id,
            extract_biography(record),
            extract_external_identifiers(record),
            extract_fundings(record),
            extract_employments(record),
            extract_educations(record),
            extract_distinctions(record),
            extract_memberships(record),
            extract_services(record),
        )

    # Don't write file if no data
    if not data:
        logger.info(f"No {section} data found; skipping file creation.")
        return

    # Write JSON output (reuse config from initial load to respect --config)
    output_path.mkdir(parents=True, exist_ok=True)
    output_file = output_path / output_filename
    output_file.write_text(json.dumps(data, indent=config.json_indent, ensure_ascii=False))

    logger.info(f"Generated: {output_file}")
    print(str(output_file))


if __name__ == "__main__":
    main()
