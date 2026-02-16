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
import sys
from pathlib import Path

from academia_orcid import SECTION_DATA, SECTION_PUBLICATIONS, VALID_SECTIONS
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
from academia_orcid.fetch import get_or_fetch_orcid_record, get_orcid_for_uin
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

    args = parser.parse_args()

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
        print(f"Using ORCID ID directly: {orcid_id}", file=sys.stderr)
    else:
        uin = args.uin
        if not args.mapping_db:
            print("Error: --mapping-db is required when using --uin", file=sys.stderr)
            sys.exit(1)

        db_path = Path(args.mapping_db)
        if not db_path.exists():
            print(f"Error: Mapping database not found: {db_path}", file=sys.stderr)
            sys.exit(1)

        orcid_id = get_orcid_for_uin(db_path, uin)
        if not orcid_id:
            print(f"Warning: No ORCID ID found for UIN {uin}; skipping.", file=sys.stderr)
            return

        print(f"Found ORCID {orcid_id} for UIN {uin}", file=sys.stderr)

    # Load ORCID record
    record = get_or_fetch_orcid_record(data_path, orcid_id, None, fetch=fetch_enabled, force=force_fetch)
    if not record:
        print(f"Warning: No ORCID record found for {orcid_id}; skipping.", file=sys.stderr)
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
        print(f"No {section} data found; skipping file creation.", file=sys.stderr)
        return

    # Write JSON output
    config = get_config()
    output_path.mkdir(parents=True, exist_ok=True)
    output_file = output_path / output_filename
    output_file.write_text(json.dumps(data, indent=config.json_indent, ensure_ascii=False))

    print(f"Generated: {output_file}", file=sys.stderr)
    print(str(output_file))


if __name__ == "__main__":
    main()
