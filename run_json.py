#!/usr/bin/env python3
"""CLI entry point for ORCID JSON export.

Parallel to run_latex.py (LaTeX), this outputs structured JSON for the
composer's YAML and Word pipelines. Same CLI contract and exit codes
(academia_orcid.cli): --uin or --orcid, --output-dir, --section, and the period
flags (--year, --acad_year, --cal_year, --semester; academia_orcid.periods).

Output:
    {output-dir}/orcid-data.json         (--section data)
    {output-dir}/orcid-publications.json (--section publications)
"""

import argparse
import json
from pathlib import Path

from academia_orcid import (
    OUTPUT_DATA_JSON,
    OUTPUT_PUBLICATIONS_JSON,
    SECTION_PUBLICATIONS,
    VALID_SECTIONS,
)
from academia_orcid.cli import (
    add_common_args,
    load_record,
    resolve_orcid_id,
    resolve_period,
    setup_from_args,
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
from academia_orcid.json_export import export_data, export_publications


def main(argv: list[str] | None = None):
    """Generate ORCID JSON export for a faculty member."""
    parser = argparse.ArgumentParser(
        description="Export ORCID data as structured JSON (composer YAML/Word pipelines)."
    )
    add_common_args(parser)
    parser.add_argument(
        "--section",
        default=SECTION_PUBLICATIONS,
        choices=VALID_SECTIONS,
        help="Section to export: publications or data",
    )
    args = parser.parse_args(argv)
    logger = setup_from_args(args, "academia_orcid.run_json")

    output_path = Path(args.output_dir)
    section = args.section
    period = resolve_period(args)
    output_filename = OUTPUT_PUBLICATIONS_JSON if section == SECTION_PUBLICATIONS else OUTPUT_DATA_JSON

    orcid_id = resolve_orcid_id(args, logger)
    if orcid_id is None:
        logger.info(f"No {section} section.")
        return
    record = load_record(args, orcid_id, logger)
    if record is None:
        logger.info(f"No {section} section.")
        return

    # Extract and export
    if section == SECTION_PUBLICATIONS:
        journal_articles, conference_papers, other_publications = extract_publications(record)

        journal_articles = filter_publications_by_period(journal_articles, period)
        conference_papers = filter_publications_by_period(conference_papers, period)
        other_publications = filter_publications_by_period(other_publications, period)

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

    output_path.mkdir(parents=True, exist_ok=True)
    output_file = output_path / output_filename
    output_file.write_text(json.dumps(data, indent=get_config().json_indent, ensure_ascii=False))

    logger.info(f"Generated: {output_file}")
    print(str(output_file))


if __name__ == "__main__":
    main()
