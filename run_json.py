#!/usr/bin/env python3
"""The section entry point: ORCID publications or profile data as structured JSON.

The faculty composer (tamu-coe-faculty-profiles) renders it in every format.
CLI contract and exit codes in academia_orcid.cli: --uin or --orcid,
--output-dir, --section and the fetch flags. Every publication is written: the
composer keeps the report period's (2026-11-13).

Output:
    {output-dir}/orcid-data.json         (--section data)
    {output-dir}/orcid-publications.json (--section publications)
No data, no file.
"""

import argparse
import json
from pathlib import Path

from academia_orcid import (
    OUTPUT_DATA_JSON,
    OUTPUT_PUBLICATIONS_JSON,
    SECTION_PUBLICATIONS,
)
from academia_orcid.cli import (
    add_common_args,
    load_record,
    resolve_orcid_id,
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
)
from academia_orcid.json_export import export_data, export_publications


def main(argv: list[str] | None = None):
    """Write the ORCID JSON for a faculty member."""
    parser = argparse.ArgumentParser(
        description="Export ORCID publications or profile data as structured JSON."
    )
    add_common_args(parser)
    args = parser.parse_args(argv)
    logger = setup_from_args(args, "academia_orcid.run_json")

    output_path = Path(args.output_dir)
    section = args.section
    output_filename = (
        OUTPUT_PUBLICATIONS_JSON if section == SECTION_PUBLICATIONS else OUTPUT_DATA_JSON
    )

    orcid_id = resolve_orcid_id(args, logger)
    if orcid_id is None:
        logger.info(f"No {section} section.")
        return
    record = load_record(args, orcid_id, logger)
    if record is None:
        logger.info(f"No {section} section.")
        return

    if section == SECTION_PUBLICATIONS:
        journal_articles, conference_papers, other_publications = extract_publications(record)
        logger.info(
            f"Found {len(journal_articles)} journal articles, "
            f"{len(conference_papers)} conference papers, {len(other_publications)} other"
        )
        data = export_publications(
            orcid_id,
            journal_articles,
            conference_papers,
            other_publications,
            fetched_at=(record.get("_cache_metadata") or {}).get("cached_at"),
        )
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

    # No data, no file: the composer goes by file existence.
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
