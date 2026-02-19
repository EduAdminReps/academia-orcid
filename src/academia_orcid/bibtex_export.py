"""BibTeX export for ORCID publication data.

Generates standard .bib file content from ORCID publication records.
Uses embedded ORCID citations (citation-type: bibtex) when available,
falling back to construction from extracted fields.

Design philosophy (see CLAUDE.md "Data Philosophy"):
ORCID is the system of record. Embedded BibTeX from ORCID is preferred
over generated entries. The --enrich flag (handled by enrich.py) can
fill gaps from DOI content negotiation but never overrides ORCID data.
"""

import html
import logging
import re
import unicodedata
from datetime import datetime, timezone

from academia_orcid.normalize import strip_html_tags

logger = logging.getLogger("academia_orcid.bibtex_export")


# ── ORCID type → BibTeX entry type ──────────────────────────────────────

ORCID_TO_BIBTEX_TYPE = {
    # Journal articles
    "journal-article": "article",
    "journal-issue": "article",
    "article-journal": "article",
    # Conference papers
    "conference-paper": "inproceedings",
    "conference-abstract": "inproceedings",
    "conference-poster": "inproceedings",
    "paper-conference": "inproceedings",
    # Books
    "book": "book",
    "edited-book": "book",
    "book-chapter": "incollection",
    "book-review": "article",
    # Dissertations
    "dissertation": "phdthesis",
    "dissertation-thesis": "phdthesis",
    # Reports and working papers
    "report": "techreport",
    "working-paper": "unpublished",
    "preprint": "unpublished",
    # Other
    "manual": "manual",
    "online-resource": "misc",
    "website": "misc",
    "other": "misc",
}

MONTH_ABBREV = {
    "01": "jan", "02": "feb", "03": "mar", "04": "apr",
    "05": "may", "06": "jun", "07": "jul", "08": "aug",
    "09": "sep", "10": "oct", "11": "nov", "12": "dec",
    "1": "jan", "2": "feb", "3": "mar", "4": "apr",
    "5": "may", "6": "jun", "7": "jul", "8": "aug",
    "9": "sep", "10": "oct", "11": "nov", "12": "dec",
}


# ── Helpers ──────────────────────────────────────────────────────────────

def _generate_cite_key(last_name: str, year: str, seen_keys: dict[str, int]) -> str:
    """Generate a stable, unique cite key.

    Format: LastName + Year, with alphabetic suffix for duplicates.
    E.g., Smith2024, Smith2024a, Smith2024b.
    """
    # ASCII-fold and strip non-alpha characters
    clean_name = unicodedata.normalize("NFKD", last_name)
    clean_name = clean_name.encode("ascii", "ignore").decode("ascii")
    clean_name = re.sub(r"[^a-zA-Z]", "", clean_name)
    if not clean_name:
        clean_name = "Unknown"

    base_key = f"{clean_name}{year or 'NoYear'}"

    if base_key not in seen_keys:
        seen_keys[base_key] = 0
        return base_key

    seen_keys[base_key] += 1
    suffix = chr(ord("a") + seen_keys[base_key] - 1)
    return f"{base_key}{suffix}"


def _get_first_author_last_name(pub: dict) -> str:
    """Extract first author's last name from raw_authors or authors field."""
    raw = pub.get("raw_authors", [])
    if raw:
        parts = raw[0].split()
        return parts[-1] if parts else "Unknown"

    # Fallback: parse from formatted authors string
    authors_str = pub.get("authors", "")
    if authors_str:
        first_author = authors_str.split(",")[0].strip()
        return first_author or "Unknown"

    return "Unknown"


def _escape_bibtex(text: str) -> str:
    """Clean text for BibTeX field values.

    Strips HTML tags but preserves LaTeX math ($...$) and commands,
    since BibTeX handles LaTeX natively.
    """
    if not text:
        return ""
    text = html.unescape(text)
    text = strip_html_tags(text)
    return text


def _format_authors_bibtex(raw_authors: list[str]) -> str:
    """Format author list for BibTeX: 'Last, First and Last, First and ...'

    No author limit — all authors are included in BibTeX output.
    """
    if not raw_authors:
        return ""

    formatted = []
    for name in raw_authors:
        name = html.unescape(name)
        parts = name.split()
        if len(parts) > 1:
            last = parts[-1]
            first = " ".join(parts[:-1])
            formatted.append(f"{last}, {first}")
        else:
            formatted.append(name)

    return " and ".join(formatted)


def _extract_cite_key_from_bibtex(bibtex_str: str) -> str | None:
    """Extract the cite key from an embedded BibTeX string."""
    match = re.match(r"@\w+\{([^,]+),", bibtex_str.strip())
    return match.group(1).strip() if match else None


def _normalize_embedded_bibtex(bibtex_str: str) -> str:
    """Clean up embedded BibTeX from ORCID (normalize whitespace)."""
    # Normalize tab-based formatting to newline-based
    text = bibtex_str.strip()
    if "\t" in text and "\n" not in text:
        text = text.replace("\t", "\n  ")
    return text


def _pub_to_bibtex_entry(pub: dict, cite_key: str) -> str:
    """Convert a single publication dict to a BibTeX entry string.

    Used as fallback when no embedded ORCID citation exists.
    """
    pub_type = pub.get("pub_type", "other")
    entry_type = ORCID_TO_BIBTEX_TYPE.get(pub_type, "misc")

    fields = []

    # Authors
    raw_authors = pub.get("raw_authors", [])
    if raw_authors:
        authors_str = _format_authors_bibtex(raw_authors)
        fields.append(f"  author = {{{authors_str}}}")

    # Title (double-braced to prevent BibTeX case mangling)
    title = pub.get("title", "")
    if title:
        clean_title = _escape_bibtex(title)
        fields.append(f"  title = {{{{{clean_title}}}}}")

    # Venue → journal or booktitle depending on entry type
    venue = pub.get("venue", "")
    if venue:
        clean_venue = _escape_bibtex(venue)
        if entry_type in ("inproceedings", "incollection"):
            fields.append(f"  booktitle = {{{clean_venue}}}")
        elif entry_type == "article":
            fields.append(f"  journal = {{{clean_venue}}}")
        else:
            fields.append(f"  publisher = {{{clean_venue}}}")

    # Year
    year = pub.get("year", "")
    if year:
        fields.append(f"  year = {{{year}}}")

    # Month (as BibTeX macro — no braces)
    month = pub.get("month", "")
    if month:
        month_name = MONTH_ABBREV.get(month)
        if month_name:
            fields.append(f"  month = {month_name}")

    # DOI
    doi = pub.get("doi", "")
    if doi:
        fields.append(f"  doi = {{{doi}}}")

    # URL
    url = pub.get("url", "")
    if url:
        fields.append(f"  url = {{{url}}}")

    # Additional fields from enrichment (if present)
    for key in ("volume", "pages", "number", "publisher", "abstract"):
        value = pub.get(key, "")
        if value:
            fields.append(f"  {key} = {{{_escape_bibtex(str(value))}}}")

    # External IDs (isbn, issn)
    ext_ids = pub.get("external_ids", {})
    if ext_ids.get("isbn"):
        fields.append(f"  isbn = {{{ext_ids['isbn']}}}")
    if ext_ids.get("issn"):
        fields.append(f"  issn = {{{ext_ids['issn']}}}")

    fields_str = ",\n".join(fields)
    return f"@{entry_type}{{{cite_key},\n{fields_str}\n}}"


# ── Main export ──────────────────────────────────────────────────────────

def export_bibtex(
    orcid_id: str,
    journal_articles: list[dict],
    conference_papers: list[dict],
    other_publications: list[dict],
) -> str:
    """Export publications as BibTeX .bib file content.

    Strategy:
    1. If a publication has an embedded ORCID citation (citation-type: bibtex),
       use it directly (ORCID is system of record).
    2. Otherwise, generate BibTeX from extracted fields.

    Args:
        orcid_id: ORCID identifier (for header comment)
        journal_articles: List of journal article dicts
        conference_papers: List of conference paper dicts
        other_publications: List of other publication dicts

    Returns:
        Complete .bib file content as string, or "" if no publications.
    """
    all_pubs = journal_articles + conference_papers + other_publications
    if not all_pubs:
        return ""

    seen_keys: dict[str, int] = {}
    entries = []
    stats = {"embedded": 0, "generated": 0}

    for pub in all_pubs:
        citation = pub.get("citation")

        # Prefer embedded BibTeX from ORCID
        if (citation and isinstance(citation, dict)
                and citation.get("citation-type") == "bibtex"):
            bibtex_str = citation.get("citation-value", "")
            if bibtex_str.strip():
                embedded_key = _extract_cite_key_from_bibtex(bibtex_str)
                if embedded_key:
                    if embedded_key in seen_keys:
                        # Duplicate key — generate a unique replacement
                        last_name = _get_first_author_last_name(pub)
                        new_key = _generate_cite_key(
                            last_name, pub.get("year", ""), seen_keys
                        )
                        bibtex_str = re.sub(
                            r"(@\w+\{)[^,]+,",
                            rf"\g<1>{new_key},",
                            bibtex_str,
                            count=1,
                        )
                    else:
                        seen_keys[embedded_key] = 0

                entries.append(_normalize_embedded_bibtex(bibtex_str))
                stats["embedded"] += 1
                continue

        # Fallback: generate from extracted fields
        last_name = _get_first_author_last_name(pub)
        cite_key = _generate_cite_key(last_name, pub.get("year", ""), seen_keys)
        entry = _pub_to_bibtex_entry(pub, cite_key)
        entries.append(entry)
        stats["generated"] += 1

    logger.info(
        f"BibTeX export: {stats['embedded']} from ORCID citations, "
        f"{stats['generated']} generated from metadata"
    )

    header = (
        f"% BibTeX export from ORCID record: {orcid_id}\n"
        f"% Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        f"% Source: https://orcid.org/{orcid_id}\n"
        f"% Entries: {len(entries)} total "
        f"({stats['embedded']} from ORCID, {stats['generated']} generated)\n"
        f"%\n"
    )

    return header + "\n\n".join(entries) + "\n"
