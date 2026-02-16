"""JSON export for ORCID data — format-agnostic structured output.

Reuses extract.py functions (which already return plain dicts/lists)
and wraps them in a standard JSON envelope with _meta section.

Text fields are cleaned via normalize.clean_for_plaintext() to strip
HTML markup and convert sub/superscripts to Unicode.
"""

from datetime import datetime, timezone

from academia_orcid.normalize import clean_for_plaintext


def _clean_pub(pub: dict) -> dict:
    """Return a copy with the title cleaned for plain-text output."""
    cleaned = dict(pub)
    if cleaned.get("title"):
        cleaned["title"] = clean_for_plaintext(cleaned["title"])
    return cleaned


def export_data(
    orcid_id: str,
    biography: str | None,
    external_identifiers: list[dict],
    fundings: list[dict],
    employments: list[dict],
    educations: list[dict],
    distinctions: list[dict],
    memberships: list[dict],
    services: list[dict],
) -> dict:
    """Export ORCID data fields as a JSON-serializable dict.

    Args:
        orcid_id: ORCID identifier
        biography: Biography text or None
        external_identifiers: List of external ID dicts
        fundings: List of funding dicts
        employments: List of employment dicts
        educations: List of education dicts
        distinctions: List of distinction dicts
        memberships: List of membership dicts
        services: List of service dicts

    Returns:
        Dict ready for JSON serialization
    """
    has_content = any([
        biography,
        external_identifiers,
        fundings,
        employments,
        educations,
        distinctions,
        memberships,
        services,
    ])

    if not has_content:
        return {}

    clean_bio = clean_for_plaintext(biography) if biography else biography

    return {
        "_meta": {
            "section": "orcid-data",
            "orcid_id": orcid_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "biography": clean_bio,
        "employment": employments,
        "education": educations,
        "distinctions": distinctions,
        "memberships": memberships,
        "external_service": services,
        "fundings": fundings,
        "external_identifiers": external_identifiers,
    }


def export_publications(
    orcid_id: str,
    journal_articles: list[dict],
    conference_papers: list[dict],
    other_publications: list[dict],
) -> dict:
    """Export ORCID publications as a JSON-serializable dict.

    Args:
        orcid_id: ORCID identifier
        journal_articles: List of journal article dicts
        conference_papers: List of conference paper dicts
        other_publications: List of other publication dicts

    Returns:
        Dict ready for JSON serialization
    """
    total = len(journal_articles) + len(conference_papers) + len(other_publications)

    if total == 0:
        return {}

    return {
        "_meta": {
            "section": "orcid-publications",
            "orcid_id": orcid_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_count": total,
        },
        "journal_articles": [_clean_pub(p) for p in journal_articles],
        "conference_papers": [_clean_pub(p) for p in conference_papers],
        "other_publications": [_clean_pub(p) for p in other_publications],
    }
