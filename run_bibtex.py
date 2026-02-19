#!/usr/bin/env python3
"""CLI entry point for ORCID BibTeX export.

Parallel to run_latex.py (LaTeX) and run_json.py (JSON), this outputs
a .bib file. Same CLI contract: --uin, --output-dir, --year.

Output:
    {output-dir}/orcid-publications.bib
"""

import argparse
import logging
import sys
from pathlib import Path

from academia_orcid.config import get_config
from academia_orcid.logging_config import setup_logging
from academia_orcid.extract import (
    extract_publications,
    filter_publications_by_year,
    parse_year_filter,
)
from academia_orcid.cli import validate_uin
from academia_orcid.fetch import get_or_fetch_orcid_record, get_orcid_for_uin, validate_orcid_id
from academia_orcid.bibtex_export import export_bibtex


def main():
    """Generate ORCID BibTeX export for a faculty member."""
    parser = argparse.ArgumentParser(
        description="Export ORCID publications as BibTeX (.bib)."
    )
    parser.add_argument("--uin", default=None, help="Faculty UIN")
    parser.add_argument("--orcid", default=None, help="ORCID ID directly")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--data-dir", default=".", help="Base directory for ORCID cache")
    parser.add_argument(
        "--year", default=None,
        help="Year filter (YYYY-YYYY, YYYY, or 'all').",
    )
    parser.add_argument("--fetch", action="store_true", default=True)
    parser.add_argument("--no-fetch", action="store_true")
    parser.add_argument("--force-fetch", action="store_true")
    parser.add_argument("--mapping-db", default=None, help="Path to SQLite with orcid_mapping")
    parser.add_argument(
        "--enrich", action="store_true",
        help="Enrich publications via DOI content negotiation (fills gaps)",
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
    logger = logging.getLogger("academia_orcid.run_bibtex")

    # Load configuration
    config_file = Path(args.config) if args.config else None
    get_config(config_file)

    if not args.uin and not args.orcid:
        parser.error("Either --uin or --orcid is required")

    fetch_enabled = args.fetch and not args.no_fetch
    force_fetch = args.force_fetch
    data_path = Path(args.data_dir)
    output_path = Path(args.output_dir)
    year_filter = parse_year_filter(args.year)

    # Resolve ORCID ID
    if args.orcid:
        orcid_id = args.orcid

        if not validate_orcid_id(orcid_id):
            logger.error(f"Invalid ORCID ID format: {orcid_id}")
            logger.error("ORCID IDs must match the pattern: XXXX-XXXX-XXXX-XXXX")
            sys.exit(1)

        logger.info(f"Using ORCID ID directly: {orcid_id}")
    else:
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

        orcid_id = get_orcid_for_uin(db_path, uin)
        if not orcid_id:
            logger.warning(f"No ORCID ID found for UIN {uin}; skipping.")
            return

        logger.info(f"Found ORCID {orcid_id} for UIN {uin}")

    # Load ORCID record
    record = get_or_fetch_orcid_record(data_path, orcid_id, None, fetch=fetch_enabled, force=force_fetch)
    if not record:
        logger.warning(f"No ORCID record found for {orcid_id}; skipping.")
        return

    # Extract and export
    journal_articles, conference_papers, other_publications = extract_publications(record)

    if year_filter:
        journal_articles = filter_publications_by_year(journal_articles, year_filter)
        conference_papers = filter_publications_by_year(conference_papers, year_filter)
        other_publications = filter_publications_by_year(other_publications, year_filter)

    # Optional DOI enrichment
    if args.enrich:
        from academia_orcid.enrich import enrich_publications
        logger.info("Enriching publications via DOI content negotiation...")
        journal_articles = enrich_publications(journal_articles)
        conference_papers = enrich_publications(conference_papers)
        other_publications = enrich_publications(other_publications)

    bibtex_content = export_bibtex(orcid_id, journal_articles, conference_papers, other_publications)

    if not bibtex_content:
        logger.info("No publications found; skipping .bib file creation.")
        return

    output_path.mkdir(parents=True, exist_ok=True)
    bib_file = output_path / "orcid-publications.bib"
    bib_file.write_text(bibtex_content, encoding="utf-8")

    logger.info(f"Generated: {bib_file}")
    print(str(bib_file))


if __name__ == "__main__":
    main()
