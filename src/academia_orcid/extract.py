"""Extract publication and data fields from ORCID records."""

import html
import logging
import re

from .periods import Period
from .schema import CONFERENCE_PAPER_TYPES, JOURNAL_ARTICLE_TYPES

# Module logger
logger = logging.getLogger("academia_orcid.extract")


def filter_publications_by_period(publications: list[dict], period: Period) -> list[dict]:
    """Keep the publications dated inside the report period.

    All years (no flag, or ``all``): every publication, undated ones included.
    A period: a publication with a month is kept when that month's term is in the
    period, one with only a year when that calendar year overlaps it (with
    ``--year 2024``, fiscal: Fall 2023 + Spring 2024, a 2023 work dated March is
    left out). A publication with no year, or an unparseable one, is left out of
    every period report and shown only in all-years reports (owner, 2026-11-12;
    audit ORC-16).
    """
    if period.is_all:
        return publications
    kept = []
    for pub in publications:
        year = str(pub.get("year") or "").strip()
        if re.fullmatch(r"\d{4}", year) and period.overlaps_date(year, pub.get("month") or None):
            kept.append(pub)
    return kept


def _obj(parent: object, key: str) -> dict:
    """``parent[key]`` if it is a dict, else {}: ORCID sends null for missing objects
    (``"publication-date": null`` on undated works; audit ORC-02)."""
    value = parent.get(key) if isinstance(parent, dict) else None
    return value if isinstance(value, dict) else {}


def _value(parent: object, key: str) -> str:
    """The ``value`` of ``parent[key]`` (ORCID's {"value": ...} wrapper), or ""."""
    value = _obj(parent, key).get("value")
    return str(value).strip() if value is not None else ""


_DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:www\.)?(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
_DOI_RE = re.compile(r"10\.\d{4,9}/\S+")


def normalize_doi(raw: object) -> str:
    """A bare DOI (``10.xxxx/...``, case as written) from any form ORCID holds
    (URL, ``doi:`` prefix); "" if it is not a DOI at all (audit ORC-06)."""
    text = _DOI_PREFIX_RE.sub("", str(raw or "").strip()).strip()
    return text if _DOI_RE.fullmatch(text) else ""


def _work_doi(external_ids: list) -> str:
    """The work's own DOI: relationship ``self`` first, else one with no
    relationship; never ``part-of`` (a chapter's book), so a chapter whose only
    DOI is its book's shows none (owner, 2026-11-12; audit ORC-06)."""
    own, unmarked = "", ""
    for eid in external_ids:
        if not isinstance(eid, dict) or str(eid.get("external-id-type", "")).lower() != "doi":
            continue
        doi = normalize_doi(eid.get("external-id-value"))
        relationship = str(eid.get("external-id-relationship") or "").lower()
        if doi and relationship == "self" and not own:
            own = doi
        elif doi and not relationship and not unmarked:
            unmarked = doi
    return own or unmarked


def split_name(raw: str) -> tuple[str, str]:
    """(family, given) from an ORCID credit-name, which comes as "Given Family"
    (44%) or "Family, Given" (56%; audit ORC-01). A name ending in one or two
    capitals is family first too: "Doe J", "Smith JA", "Smith John A" (an
    initial never follows the family name; in 299 of the cache's 306 two-word
    cases the capitals are initials). Three capitals ("Min KIM") read as a surname."""
    name = " ".join(str(raw).split())
    if "," in name:
        family, _, given = name.partition(",")
        return family.strip(), given.replace(",", " ").strip()
    parts = name.split(" ")
    if len(parts) == 1:
        return name, ""
    if re.fullmatch(r"[A-Z]{1,2}\.?", parts[-1]) and not re.fullmatch(r"[A-Z]{1,2}\.?", parts[0]):
        return parts[0], " ".join(parts[1:])
    return parts[-1], " ".join(parts[:-1])


def _name_parts(raw: str) -> dict[str, str]:
    """{"family", "given"} for one credit name (``split_name``): the structured
    name the composer renders as "Family, F.M." (``author_names``; owner, 2026-11-13)."""
    family, given = split_name(raw)
    return {"family": family, "given": given}


def _title_key(pub: dict) -> str:
    """Title, lower-case, letters and digits only, for spotting the same work twice."""
    return re.sub(r"[^0-9a-z]+", "", re.sub(r"<[^>]+>", "", pub.get("title", "")).lower())


# A title this short ("Editorial", "Preface") does not identify a work on its own.
MIN_TITLE_KEY = 20


def collapse_duplicates(publications: list[dict]) -> list[dict]:
    """Drop the second and later copies of one work (owner, 2026-11-12; audit ORC-10).

    ORCID groups works by shared identifiers only, so a work imported once with a
    DOI and once without lands in two groups. Two entries are the same work when
    they have the same DOI, or, when either lacks one, the same type, title (at
    least ``MIN_TITLE_KEY`` letters and digits) and year. Works with a DOI are
    kept first, then the input order decides: callers pass journal articles,
    then conference papers, then the rest, so one DOI filed under two types stays
    with the journal article.
    """
    seen_doi: set[str] = set()
    seen_title: set[tuple] = set()
    kept_ids: set[int] = set()
    ordered = sorted(enumerate(publications), key=lambda item: not item[1].get("doi"))
    for index, pub in ordered:
        doi = pub.get("doi", "").lower()  # DOIs are case-insensitive
        key = _title_key(pub)
        title_key = (pub.get("pub_type", ""), key, pub.get("year", ""))
        if doi and doi in seen_doi:
            continue
        if len(key) >= MIN_TITLE_KEY and title_key in seen_title:
            continue
        if doi:
            seen_doi.add(doi)
        if len(key) >= MIN_TITLE_KEY:
            seen_title.add(title_key)
        kept_ids.add(index)
    return [pub for index, pub in enumerate(publications) if index in kept_ids]


def extract_publications(record: dict) -> tuple[list, list, list]:
    """Extract journal articles, conference papers, and other from ORCID record.

    One entry per work, duplicates collapsed (``collapse_duplicates``). A work
    whose date, title, contributors or ids are null keeps what it has: an undated
    work is listed in all-years reports (audit ORC-02). Authors are every credit
    name as written (``raw_authors``) and as {family, given} (``author_names``);
    the composer renders them.
    """
    works = _obj(_obj(record, "activities-summary"), "works").get("group") or []

    entries = []
    for work_group in works:
        summaries = (work_group or {}).get("work-summary") or []
        work = summaries[0] if summaries and isinstance(summaries[0], dict) else None
        if work is None:
            continue
        try:
            # Markup kept for the composer; line breaks and indentation collapsed.
            title = " ".join(html.unescape(_value(_obj(work, "title"), "title")).split())
            title = title or "Untitled"
            date = _obj(work, "publication-date")
            author_names = [
                html.unescape(_value(contributor, "credit-name"))
                for contributor in (_obj(work, "contributors").get("contributor") or [])
                if _value(contributor, "credit-name")
            ]
            venue = html.unescape(_value(work, "journal-title")) or html.unescape(
                str(_obj(work, "conference").get("name") or "")
            )
            external_ids = _obj(work, "external-ids").get("external-id") or []
            all_external_ids = {
                str(eid.get("external-id-type")): str(eid.get("external-id-value"))
                for eid in external_ids
                if isinstance(eid, dict)
                and eid.get("external-id-type")
                and eid.get("external-id-value")
            }
            doi = _work_doi(external_ids)
            all_external_ids.pop("doi", None)
            if doi:
                all_external_ids["doi"] = doi
            entries.append(
                {
                    "raw_authors": author_names,
                    "author_names": [_name_parts(name) for name in author_names],
                    "title": title,
                    "venue": venue,
                    "year": _value(date, "year"),
                    "month": _value(date, "month"),
                    "doi": doi,
                    "url": _value(work, "url"),
                    "pub_type": str(work.get("type") or "").lower(),
                    "external_ids": all_external_ids,
                    "citation": work.get("citation"),
                }
            )
        except (AttributeError, TypeError, ValueError) as e:
            # Not expected with the null-safe reads above; say which work, so a
            # real parsing bug is visible rather than a silent gap.
            logger.warning(f"Skipping work {work.get('put-code')}: {type(e).__name__}: {e}")

    def category(pub: dict) -> int:
        return (
            0
            if pub["pub_type"] in JOURNAL_ARTICLE_TYPES
            else (1 if pub["pub_type"] in CONFERENCE_PAPER_TYPES else 2)
        )

    entries.sort(key=category)
    entries = collapse_duplicates(entries)

    def year_key(pub: dict) -> int:
        return int(pub["year"]) if re.fullmatch(r"\d{4}", pub["year"]) else 0

    lists: tuple[list, list, list] = ([], [], [])
    for pub in entries:
        lists[category(pub)].append(pub)
    for publications in lists:
        publications.sort(key=year_key, reverse=True)
    return lists


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
    identifiers: list[dict] = []
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
            identifiers.append(
                {
                    "type": html.unescape(id_type),
                    "value": html.unescape(id_value),
                    "url": url,
                }
            )

    return identifiers


def extract_affiliation_items(record: dict, section_name: str, summary_key: str) -> list[dict]:
    """Extract items from an affiliation-based section (employments, educations, etc.)."""
    items: list[dict] = []
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

            items.append(
                {
                    "organization": html.unescape(org_name) if org_name else "",
                    "location": location,
                    "role": html.unescape(role) if role else "",
                    "department": html.unescape(department) if department else "",
                    "start_year": start_year,
                    "end_year": end_year,
                }
            )

    # Sort by start year (descending), then by organization name
    items.sort(key=lambda x: x.get("start_year", "0") or "0", reverse=True)

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
    items: list[dict] = []
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

            items.append(
                {
                    "title": html.unescape(title) if title else "",
                    "organization": html.unescape(org_name) if org_name else "",
                    "type": funding_type,
                    "start_year": start_year,
                    "end_year": end_year,
                }
            )

    # Sort by start year (descending)
    items.sort(key=lambda x: x.get("start_year", "0") or "0", reverse=True)

    return items
