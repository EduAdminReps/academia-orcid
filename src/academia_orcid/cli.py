"""Command-line interface for generating ORCID LaTeX sections."""

import argparse
import re
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
from academia_orcid.fetch import (
    get_or_fetch_orcid_record,
    get_orcid_for_uin,
    validate_orcid_id,
)
from academia_orcid.latex import generate_data_latex, generate_latex, generate_unavailable_latex


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


def _write_unavailable(output_path: Path, output_filename: str, section: str, reason: str):
    """Write a placeholder LaTeX file when ORCID data is unavailable."""
    output_path.mkdir(parents=True, exist_ok=True)
    section_file = output_path / output_filename
    section_file.write_text(generate_unavailable_latex(section, reason))
    print(f"Generated (placeholder): {section_file}", file=sys.stderr)
    print(str(section_file))


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
    parser.add_argument(
        "--year",
        default=None,
        help="Year filter for publications (YYYY-YYYY range, YYYY single year, or 'all'). "
             "Ignored for --section data."
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        default=True,
        help="Fetch ORCID record from API if not in cache (default: True)"
    )
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="Do not fetch from API, only use cached records"
    )
    parser.add_argument(
        "--force-fetch",
        action="store_true",
        help="Always fetch from API, even if cached record exists (refreshes cache)"
    )
    parser.add_argument(
        "--mapping-db",
        default=None,
        help="Path to SQLite database with orcid_mapping table (required when using --uin)"
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to YAML configuration file (optional, defaults to .academia-orcid.yaml)"
    )

    args = parser.parse_args()

    # Load configuration (if specified via --config, or from default locations)
    config_file = Path(args.config) if args.config else None
    config = get_config(config_file)
    print(f"Using configuration (cache TTL: {config.cache_ttl}s, API timeout: {config.api_timeout}s)", file=sys.stderr)

    # Validate: need either --uin or --orcid
    if not args.uin and not args.orcid:
        parser.error("Either --uin or --orcid is required")

    # Handle fetch flags
    fetch_enabled = args.fetch and not args.no_fetch
    force_fetch = args.force_fetch

    data_path = Path(args.data_dir)
    output_path = Path(args.output_dir)
    section = args.section
    year_filter = parse_year_filter(args.year) if section == SECTION_PUBLICATIONS else None

    # Log year filter status
    if args.year and section == SECTION_DATA:
        print("Note: --year is ignored for --section data (all data included)", file=sys.stderr)
    elif year_filter:
        print(f"Year filter: {year_filter[0]}-{year_filter[1]}", file=sys.stderr)

    # Determine output file based on section type
    if section == SECTION_PUBLICATIONS:
        output_filename = "orcid-publications.tex"
    else:
        output_filename = "orcid-data.tex"

    # Resolve ORCID ID: either directly provided or looked up from UIN
    if args.orcid:
        # Direct ORCID ID provided — skip UIN mapping
        orcid_id = args.orcid

        # Validate ORCID ID format
        if not validate_orcid_id(orcid_id):
            print(f"Error: Invalid ORCID ID format: {orcid_id}", file=sys.stderr)
            print("ORCID IDs must match the pattern: XXXX-XXXX-XXXX-XXXX", file=sys.stderr)
            sys.exit(1)

        dept = None
        print(f"Using ORCID ID directly: {orcid_id}", file=sys.stderr)
    else:
        # UIN provided — look up ORCID ID from mapping database
        uin = args.uin

        # Validate UIN format
        if not validate_uin(uin):
            print(f"Error: Invalid UIN format: {uin}", file=sys.stderr)
            print("UINs must be exactly 9 digits", file=sys.stderr)
            sys.exit(1)

        if not args.mapping_db:
            print("Error: --mapping-db is required when using --uin", file=sys.stderr)
            sys.exit(1)

        db_path = Path(args.mapping_db)
        if not db_path.exists():
            print(f"Error: Mapping database not found: {db_path}", file=sys.stderr)
            sys.exit(1)

        orcid_id = get_orcid_for_uin(db_path, uin)
        dept = None

        if not orcid_id:
            reason = "No ORCID ID on file for this faculty member."
            print(f"Warning: No ORCID ID found for UIN {uin}; writing placeholder.", file=sys.stderr)
            _write_unavailable(output_path, output_filename, section, reason)
            return

        print(f"Found ORCID {orcid_id} for UIN {uin}", file=sys.stderr)

    # Load ORCID record from cache, or fetch from API if not cached
    record = get_or_fetch_orcid_record(data_path, orcid_id, dept, fetch=fetch_enabled, force=force_fetch)
    if not record:
        reason = f"ORCID record unavailable for {orcid_id}."
        print(f"Warning: No ORCID record found for {orcid_id}; writing placeholder.", file=sys.stderr)
        _write_unavailable(output_path, output_filename, section, reason)
        return

    if section == SECTION_PUBLICATIONS:
        # Extract publications
        journal_articles, conference_papers, other_publications = extract_publications(record)
        total_before = len(journal_articles) + len(conference_papers) + len(other_publications)

        # Apply year filter if specified
        if year_filter:
            journal_articles = filter_publications_by_year(journal_articles, year_filter)
            conference_papers = filter_publications_by_year(conference_papers, year_filter)
            other_publications = filter_publications_by_year(other_publications, year_filter)
            total_after = len(journal_articles) + len(conference_papers) + len(other_publications)
            print(f"Found {total_before} publications, {total_after} after year filter ({year_filter[0]}-{year_filter[1]})", file=sys.stderr)
        else:
            print(f"Found {len(journal_articles)} journal articles, {len(conference_papers)} conference papers, {len(other_publications)} other", file=sys.stderr)

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

        print(f"Found: {len(external_identifiers)} external IDs, {len(fundings)} fundings, "
              f"{len(employments)} employments, {len(educations)} educations, "
              f"{len(distinctions)} distinctions, {len(memberships)} memberships, "
              f"{len(services)} services", file=sys.stderr)

        # Generate LaTeX
        latex = generate_data_latex(
            orcid_id, biography, external_identifiers, fundings,
            employments, educations, distinctions, memberships, services
        )

    # Don't write file if no data (composer uses file existence to decide inclusion)
    if not latex:
        print(f"No {section} data found; skipping file creation.", file=sys.stderr)
        return

    # Write output
    output_path.mkdir(parents=True, exist_ok=True)
    section_file = output_path / output_filename
    section_file.write_text(latex)

    print(f"Generated: {section_file}", file=sys.stderr)
    print(str(section_file))
