"""Extract publication and data fields from ORCID records."""

import html
import logging
import sys

from .config import get_config

# Module logger
logger = logging.getLogger("academia_orcid.extract")


def parse_year_filter(year_arg: str | None) -> tuple[int, int] | None:
    """Parse year argument into a (start_year, end_year) tuple.

    Formats:
        - "YYYY-YYYY": Academic year range (e.g., "2024-2025")
        - "YYYY": Single calendar year (e.g., "2024" -> 2024-2024)
        - "all": Include all data (returns None)
        - None: No filter specified (returns None)

    Returns:
        Tuple of (start_year, end_year) as integers, or None for no filtering.
    """
    if year_arg is None or year_arg.lower() == "all":
        return None

    year_arg = year_arg.strip()

    # Range format: YYYY-YYYY
    if "-" in year_arg:
        parts = year_arg.split("-")
        if len(parts) == 2:
            try:
                start = int(parts[0])
                end = int(parts[1])

                # Validate year bounds (1900-2100 is reasonable range)
                if start < 1900 or start > 2100:
                    logger.warning(f"Start year {start} out of reasonable range (1900-2100), ignoring filter")
                    return None
                if end < 1900 or end > 2100:
                    logger.warning(f"End year {end} out of reasonable range (1900-2100), ignoring filter")
                    return None

                # Validate start <= end
                if start > end:
                    logger.warning(f"Invalid year range '{year_arg}' (start > end), ignoring filter")
                    return None

                return (start, end)
            except ValueError:
                logger.warning(f"Invalid year range '{year_arg}', ignoring filter")
                return None

    # Single year format: YYYY
    try:
        year = int(year_arg)

        # Validate year bounds
        if year < 1900 or year > 2100:
            logger.warning(f"Year {year} out of reasonable range (1900-2100), ignoring filter")
            return None

        return (year, year)
    except ValueError:
        logger.warning(f"Invalid year '{year_arg}', ignoring filter")
        return None


def filter_publications_by_year(
    publications: list[dict],
    year_range: tuple[int, int] | None
) -> list[dict]:
    """Filter publications to only include those within the year range.

    Args:
        publications: List of publication dicts with 'year' field
        year_range: Tuple of (start_year, end_year) or None for no filtering

    Returns:
        Filtered list of publications
    """
    if year_range is None:
        return publications

    start_year, end_year = year_range
    filtered = []

    for pub in publications:
        pub_year_str = pub.get("year", "")
        if not pub_year_str:
            # Include publications with no year (can't filter them out)
            filtered.append(pub)
            continue

        try:
            pub_year = int(pub_year_str)
            if start_year <= pub_year <= end_year:
                filtered.append(pub)
        except ValueError:
            # Include publications with unparseable years
            filtered.append(pub)

    return filtered


def extract_publications(record: dict) -> tuple[list, list, list]:
    """Extract journal articles, conference papers, and other from ORCID record."""
    journal_articles = []
    conference_papers = []
    other_publications = []

    activities = record.get("activities-summary", {})
    works = activities.get("works", {}).get("group", [])

    if not works:
        return journal_articles, conference_papers, other_publications

    for work_group in works:
        try:
            work_summaries = work_group.get("work-summary", [])
            if not work_summaries:
                continue

            work_details = work_summaries[0]
            if not work_details:
                continue

            pub_type = work_details.get("type", "").lower()

            # Get title
            raw_title = work_details.get("title", {}).get("title", {}).get("value", "Untitled")
            title = html.unescape(raw_title)

            # Get year
            year = work_details.get("publication-date", {}).get("year", {}).get("value", "")

            # Get authors
            contributors = work_details.get("contributors", {})
            if contributors:
                contributors = contributors.get("contributor", [])
            else:
                contributors = []

            author_names = []
            for contributor in contributors:
                if contributor:
                    credit_name = contributor.get("credit-name", {})
                    if credit_name:
                        raw_name = credit_name.get("value", "")
                        if raw_name:
                            name = html.unescape(raw_name)
                            author_names.append(name)

            # Get journal/venue name
            venue = ""
            journal_title = work_details.get("journal-title", {})
            if journal_title:
                raw_venue = journal_title.get("value", "")
                if raw_venue:
                    venue = html.unescape(raw_venue)

            if not venue:
                conference = work_details.get("conference", {})
                if conference:
                    raw_conf = conference.get("name", "")
                    if raw_conf:
                        venue = html.unescape(raw_conf)

            # Get month if available
            month = ""
            pub_date = work_details.get("publication-date", {})
            if pub_date:
                month_obj = pub_date.get("month")
                if month_obj and isinstance(month_obj, dict):
                    month = month_obj.get("value", "")

            # Get URL if available
            url = ""
            url_obj = work_details.get("url")
            if url_obj and isinstance(url_obj, dict):
                url = url_obj.get("value", "")

            # Collect all external IDs
            doi = ""
            all_external_ids = {}
            external_ids = work_details.get("external-ids", {})
            if external_ids:
                external_id_list = external_ids.get("external-id", [])
                if external_id_list:
                    for eid in external_id_list:
                        if eid:
                            eid_type = eid.get("external-id-type", "")
                            eid_value = eid.get("external-id-value", "")
                            if eid_type and eid_value:
                                all_external_ids[eid_type] = eid_value
                                if eid_type == "doi" and not doi:
                                    doi = eid_value

            # Get citation data if present (may contain BibTeX)
            citation_data = work_details.get("citation")

            # Format authors (IEEE style: Last, F.M.)
            config = get_config()
            author_limit = config.author_limit
            formatted_authors = []
            for author in author_names[:author_limit]:  # Limit to configured number of authors
                parts = author.split()
                if len(parts) > 1:
                    last_name = parts[-1]
                    initials = ''.join(word[0] + '.' for word in parts[:-1])
                    formatted_authors.append(f"{last_name}, {initials}")
                else:
                    formatted_authors.append(author)

            if len(author_names) > author_limit:
                formatted_authors.append("et al.")

            pub_entry = {
                "authors": ", ".join(formatted_authors),
                "raw_authors": list(author_names),
                "title": title,
                "venue": venue,
                "year": year,
                "month": month,
                "doi": doi,
                "url": url,
                "pub_type": pub_type,
                "external_ids": all_external_ids,
                "citation": citation_data,
            }

            # Categorize
            if pub_type in ["journal-article", "journal-issue", "article-journal"]:
                journal_articles.append(pub_entry)
            elif pub_type in ["conference-paper", "conference-abstract", "conference-poster", "paper-conference"]:
                conference_papers.append(pub_entry)
            else:
                # Include other types (books, book chapters, etc.)
                other_publications.append(pub_entry)

        except (KeyError, AttributeError, TypeError, ValueError, IndexError) as e:
            # Skip malformed work entries (missing fields, unexpected structure)
            logger.warning(f"Skipping malformed work entry: {type(e).__name__}")
            continue

    # Sort by year (descending)
    journal_articles.sort(key=lambda x: x.get("year", "0"), reverse=True)
    conference_papers.sort(key=lambda x: x.get("year", "0"), reverse=True)
    other_publications.sort(key=lambda x: x.get("year", "0"), reverse=True)

    return journal_articles, conference_papers, other_publications


def extract_biography(record: dict) -> str | None:
    """Extract biography text from ORCID record."""
    person = record.get("person", {})
    biography = person.get("biography")
    if biography and isinstance(biography, dict):
        content = biography.get("content", "")
        if content:
            return html.unescape(content)
    return None


def extract_external_identifiers(record: dict) -> list[dict]:
    """Extract external identifiers (Scopus, ResearcherID, etc.) from ORCID record."""
    identifiers = []
    person = record.get("person", {})
    ext_ids = person.get("external-identifiers", {})

    if not ext_ids:
        return identifiers

    for ext_id in ext_ids.get("external-identifier", []):
        if not ext_id:
            continue

        id_type = ext_id.get("external-id-type", "")
        id_value = ext_id.get("external-id-value", "")
        id_url = ext_id.get("external-id-url", {})
        url = id_url.get("value", "") if id_url else ""

        if id_type and id_value:
            identifiers.append({
                "type": html.unescape(id_type),
                "value": html.unescape(id_value),
                "url": url,
            })

    return identifiers


def extract_affiliation_items(record: dict, section_name: str, summary_key: str) -> list[dict]:
    """Extract items from an affiliation-based section (employments, educations, etc.)."""
    items = []
    activities = record.get("activities-summary", {})
    section = activities.get(section_name, {})

    if not section:
        return items

    groups = section.get("affiliation-group", [])
    for group in groups:
        summaries = group.get("summaries", [])
        for summary_wrapper in summaries:
            summary = summary_wrapper.get(summary_key, {})
            if not summary:
                continue

            # Extract common fields
            org = summary.get("organization", {})
            org_name = org.get("name", "") if org else ""

            address = org.get("address", {}) if org else {}
            city = address.get("city", "")
            region = address.get("region", "")
            country = address.get("country", "")
            location_parts = [p for p in [city, region, country] if p]
            location = ", ".join(location_parts)

            role = summary.get("role-title", "")
            department = summary.get("department-name", "")

            start_date = summary.get("start-date", {})
            start_year = start_date.get("year", {}).get("value", "") if start_date else ""

            end_date = summary.get("end-date", {})
            end_year = end_date.get("year", {}).get("value", "") if end_date else ""

            items.append({
                "organization": html.unescape(org_name) if org_name else "",
                "location": location,
                "role": html.unescape(role) if role else "",
                "department": html.unescape(department) if department else "",
                "start_year": start_year,
                "end_year": end_year,
            })

    # Sort by start year (descending), then by organization name
    items.sort(key=lambda x: (x.get("start_year", "0") or "0"), reverse=True)

    return items


def extract_employments(record: dict) -> list[dict]:
    """Extract employment history from ORCID record."""
    return extract_affiliation_items(record, "employments", "employment-summary")


def extract_educations(record: dict) -> list[dict]:
    """Extract education history from ORCID record."""
    return extract_affiliation_items(record, "educations", "education-summary")


def extract_distinctions(record: dict) -> list[dict]:
    """Extract distinctions/awards from ORCID record."""
    return extract_affiliation_items(record, "distinctions", "distinction-summary")


def extract_memberships(record: dict) -> list[dict]:
    """Extract professional memberships from ORCID record."""
    return extract_affiliation_items(record, "memberships", "membership-summary")


def extract_services(record: dict) -> list[dict]:
    """Extract service activities from ORCID record."""
    return extract_affiliation_items(record, "services", "service-summary")


def extract_fundings(record: dict) -> list[dict]:
    """Extract funding/grants from ORCID record."""
    items = []
    activities = record.get("activities-summary", {})
    fundings = activities.get("fundings", {})

    if not fundings:
        return items

    groups = fundings.get("group", [])
    for group in groups:
        summaries = group.get("funding-summary", [])
        for summary in summaries:
            if not summary:
                continue

            # Get title
            title_obj = summary.get("title", {})
            title = title_obj.get("title", {}).get("value", "") if title_obj else ""

            # Get funder organization
            org = summary.get("organization", {})
            org_name = org.get("name", "") if org else ""

            # Get funding type
            funding_type = summary.get("type", "")

            # Get dates
            start_date = summary.get("start-date", {})
            start_year = start_date.get("year", {}).get("value", "") if start_date else ""

            end_date = summary.get("end-date", {})
            end_year = end_date.get("year", {}).get("value", "") if end_date else ""

            items.append({
                "title": html.unescape(title) if title else "",
                "organization": html.unescape(org_name) if org_name else "",
                "type": funding_type,
                "start_year": start_year,
                "end_year": end_year,
            })

    # Sort by start year (descending)
    items.sort(key=lambda x: (x.get("start_year", "0") or "0"), reverse=True)

    return items
