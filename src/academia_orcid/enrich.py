"""DOI content negotiation enrichment for ORCID publication data.

Opt-in enrichment that fills gaps in ORCID metadata using DOI content
negotiation (CSL-JSON via doi.org). Follows the project's Data Philosophy:
ORCID is the system of record — enrichment fills empty fields but NEVER
overrides existing ORCID data.

Usage:
    from academia_orcid.enrich import enrich_publications
    enriched = enrich_publications(publications)
"""

import logging
import time

import requests

logger = logging.getLogger("academia_orcid.enrich")

# Fields that can be filled from DOI metadata (only if empty in ORCID data)
ENRICHABLE_FIELDS = ("venue", "month", "volume", "pages", "number", "publisher", "abstract")


def fetch_doi_metadata(doi: str, timeout: int = 10) -> dict | None:
    """Fetch metadata for a DOI via content negotiation (CSL-JSON).

    Args:
        doi: DOI string (e.g., "10.1109/TSP.2024.001")
        timeout: Request timeout in seconds

    Returns:
        CSL-JSON dict if successful, None on any failure.
    """
    url = f"https://doi.org/{doi}"
    headers = {
        "Accept": "application/vnd.citationstyles.csl+json",
        "User-Agent": "academia-orcid/1.0 (mailto:engineering@tamu.edu)",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        logger.warning(f"DOI lookup timed out: {doi}")
        return None
    except requests.exceptions.HTTPError as e:
        logger.warning(f"DOI lookup HTTP error for {doi}: {e.response.status_code}")
        return None
    except (requests.exceptions.RequestException, ValueError) as e:
        logger.warning(f"DOI lookup failed for {doi}: {e}")
        return None


def _extract_month_from_csl(csl: dict) -> str:
    """Extract month string from CSL-JSON issued date-parts."""
    issued = csl.get("issued")
    if not issued:
        return ""
    date_parts = issued.get("date-parts", [])
    if date_parts and len(date_parts[0]) >= 2:
        return str(date_parts[0][1])
    return ""


def _extract_authors_from_csl(csl: dict) -> list[str]:
    """Extract author names from CSL-JSON author array.

    Returns list of "Given Family" strings.
    """
    authors = []
    for author in csl.get("author", []):
        given = author.get("given", "")
        family = author.get("family", "")
        if given and family:
            authors.append(f"{given} {family}")
        elif family:
            authors.append(family)
        elif given:
            authors.append(given)
    return authors


def enrich_publication(pub: dict, csl: dict) -> dict:
    """Merge DOI metadata into a publication dict (fill-only semantics).

    Only fills fields that are empty/missing in the ORCID data.
    Never overrides existing values.

    Args:
        pub: Publication dict from extract_publications()
        csl: CSL-JSON metadata from DOI content negotiation

    Returns:
        The same pub dict with empty fields filled where possible.
    """
    # Venue (container-title in CSL-JSON)
    if not pub.get("venue"):
        container = csl.get("container-title")
        if isinstance(container, list) and container:
            pub["venue"] = container[0]
        elif isinstance(container, str) and container:
            pub["venue"] = container

    # Month
    if not pub.get("month"):
        month = _extract_month_from_csl(csl)
        if month:
            pub["month"] = month

    # Volume
    if not pub.get("volume"):
        volume = csl.get("volume")
        if volume:
            pub["volume"] = str(volume)

    # Pages
    if not pub.get("pages"):
        page = csl.get("page")
        if page:
            pub["pages"] = str(page)

    # Issue number
    if not pub.get("number"):
        issue = csl.get("issue")
        if issue:
            pub["number"] = str(issue)

    # Publisher
    if not pub.get("publisher"):
        publisher = csl.get("publisher")
        if publisher:
            pub["publisher"] = str(publisher)

    # Abstract
    if not pub.get("abstract"):
        abstract = csl.get("abstract")
        if abstract:
            pub["abstract"] = str(abstract)

    # Raw authors (fill only if ORCID had none)
    if not pub.get("raw_authors"):
        authors = _extract_authors_from_csl(csl)
        if authors:
            pub["raw_authors"] = authors

    return pub


def _needs_enrichment(pub: dict) -> bool:
    """Check if a publication has empty fields that could be enriched."""
    for field in ENRICHABLE_FIELDS:
        if not pub.get(field):
            return True
    if not pub.get("raw_authors"):
        return True
    return False


def enrich_publications(
    publications: list[dict],
    rate_limit_delay: float = 0.3,
    timeout: int = 10,
) -> list[dict]:
    """Enrich a list of publications via DOI content negotiation.

    Only queries DOIs for publications that have missing fields.
    Respects rate limits with configurable delay between requests.

    Args:
        publications: List of publication dicts from extract_publications()
        rate_limit_delay: Delay in seconds between DOI requests
        timeout: Request timeout in seconds per DOI lookup

    Returns:
        The same list with empty fields filled where possible.
    """
    if not publications:
        return publications

    enriched_count = 0
    skipped_no_doi = 0
    skipped_complete = 0
    failed = 0

    for i, pub in enumerate(publications):
        doi = pub.get("doi", "")
        if not doi:
            skipped_no_doi += 1
            continue

        if not _needs_enrichment(pub):
            skipped_complete += 1
            continue

        # Rate limiting (skip delay before first request)
        if enriched_count > 0:
            time.sleep(rate_limit_delay)

        csl = fetch_doi_metadata(doi, timeout=timeout)
        if csl is None:
            failed += 1
            continue

        enrich_publication(pub, csl)
        enriched_count += 1

    logger.info(
        f"DOI enrichment: {enriched_count} enriched, "
        f"{skipped_no_doi} without DOI, "
        f"{skipped_complete} already complete, "
        f"{failed} failed"
    )

    return publications
