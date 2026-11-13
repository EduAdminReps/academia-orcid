#!/usr/bin/env python3
"""CLI entry point for ORCID BibTeX export.

Parallel to run_latex.py (LaTeX) and run_json.py (JSON), this outputs a .bib
file. Same CLI contract and exit codes (academia_orcid.cli): --uin or --orcid,
--output-dir, and the period flags (--year, --acad_year, --cal_year, --semester;
academia_orcid.periods).

Output:
    {output-dir}/orcid-publications.bib
"""

import argparse
from pathlib import Path

from academia_orcid import OUTPUT_PUBLICATIONS_BIB
from academia_orcid.bibtex_export import export_bibtex
from academia_orcid.cli import (
    add_common_args,
    load_record,
    resolve_orcid_id,
    resolve_period,
    setup_from_args,
)
from academia_orcid.extract import (
    extract_publications,
    filter_publications_by_period,
)


def main(argv: list[str] | None = None):
    """Generate ORCID BibTeX export for a faculty member."""
    parser = argparse.ArgumentParser(
        description="Export ORCID publications as BibTeX (.bib)."
    )
    add_common_args(parser)
    parser.add_argument(
        "--enrich", action="store_true",
        help="Enrich publications via DOI content negotiation (fills gaps)",
    )
    args = parser.parse_args(argv)
    logger = setup_from_args(args, "academia_orcid.run_bibtex")

    output_path = Path(args.output_dir)
    period = resolve_period(args)

    orcid_id = resolve_orcid_id(args, logger)
    if orcid_id is None:
        logger.info("No .bib file.")
        return
    record = load_record(args, orcid_id, logger)
    if record is None:
        logger.info("No .bib file.")
        return

    # Extract and export
    journal_articles, conference_papers, other_publications = extract_publications(record)

    journal_articles = filter_publications_by_period(journal_articles, period)
    conference_papers = filter_publications_by_period(conference_papers, period)
    other_publications = filter_publications_by_period(other_publications, period)

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
    bib_file = output_path / OUTPUT_PUBLICATIONS_BIB
    bib_file.write_text(bibtex_content, encoding="utf-8")

    logger.info(f"Generated: {bib_file}")
    print(str(bib_file))


if __name__ == "__main__":
    main()
