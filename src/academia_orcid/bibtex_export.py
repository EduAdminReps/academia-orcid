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

from academia_orcid.extract import split_name
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
    "01": "jan",
    "02": "feb",
    "03": "mar",
    "04": "apr",
    "05": "may",
    "06": "jun",
    "07": "jul",
    "08": "aug",
    "09": "sep",
    "10": "oct",
    "11": "nov",
    "12": "dec",
    "1": "jan",
    "2": "feb",
    "3": "mar",
    "4": "apr",
    "5": "may",
    "6": "jun",
    "7": "jul",
    "8": "aug",
    "9": "sep",
}


# ── Helpers ──────────────────────────────────────────────────────────────

# An embedded citation is used only if it starts like a BibTeX entry: "@type{key,"
# (spaces allowed: 1,602 cached citations read "@article {key,"). ORCID also
# stores HTML pages and formatted references typed "bibtex" (202 in the cache);
# those get a generated entry instead (audit ORC-07).
_ENTRY_HEAD = re.compile(r"^\s*@\s*(\w+)\s*\{\s*([^,\s]*)\s*,")


def _key_suffixes():
    """a, b, ..., z, aa, ab, ...: the suffixes that tell equal base keys apart."""
    n = 1
    while True:
        suffix, k = "", n
        while k:
            k, r = divmod(k - 1, 26)
            suffix = chr(ord("a") + r) + suffix
        yield suffix
        n += 1


def _claim_key(key: str, used: set[str]) -> str:
    """``key``, or ``key`` plus the first free suffix; recorded in ``used``.

    ``used`` holds every key emitted so far, embedded or generated, casefolded
    (BibTeX and biber report keys differing only in case as repeated entries).
    """
    candidate = key
    if candidate.casefold() in used:
        candidate = next(key + s for s in _key_suffixes() if (key + s).casefold() not in used)
    used.add(candidate.casefold())
    return candidate


def _generate_cite_key(last_name: str, year: str, used: set[str]) -> str:
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
    return _claim_key(f"{clean_name}{year or 'NoYear'}", used)


def _get_first_author_last_name(pub: dict) -> str:
    """Extract first author's last name from raw_authors or authors field."""
    raw = pub.get("raw_authors", [])
    if raw:
        family, _ = split_name(html.unescape(raw[0]))
        return family or "Unknown"

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
        family, given = split_name(html.unescape(name))  # either credit-name order (ORC-01)
        formatted.append(f"{family}, {given}" if given else family)

    return " and ".join(formatted)


def _extract_cite_key_from_bibtex(bibtex_str: str) -> str | None:
    """The cite key of an embedded BibTeX entry; None if it has none or is not BibTeX."""
    match = _ENTRY_HEAD.match(bibtex_str)
    return (match.group(2) or None) if match else None


def _is_bibtex_entry(text: str) -> bool:
    """Whether an embedded "bibtex" citation is a BibTeX entry at all."""
    return bool(_ENTRY_HEAD.match(text))


def _set_cite_key(bibtex_str: str, key: str) -> str:
    """The entry with its cite key replaced (or supplied, if it had none)."""
    return _ENTRY_HEAD.sub(lambda m: f"@{m.group(1)}{{{key},", bibtex_str.strip(), count=1)


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
    1. If a publication has an embedded ORCID citation (citation-type: bibtex)
       that is a BibTeX entry, use it (ORCID is system of record), with its key
       made unique if another entry already uses it.
    2. Otherwise, generate BibTeX from extracted fields.

    Every key is unique in the file, case-insensitively (audit ORC-07).

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

    used: set[str] = set()
    entries = []
    stats = {"embedded": 0, "generated": 0}

    for pub in all_pubs:
        citation = pub.get("citation")

        # Prefer embedded BibTeX from ORCID, if it is BibTeX
        if citation and isinstance(citation, dict) and citation.get("citation-type") == "bibtex":
            bibtex_str = citation.get("citation-value") or ""
            if _is_bibtex_entry(bibtex_str):
                embedded_key = _extract_cite_key_from_bibtex(bibtex_str)
                if embedded_key and embedded_key.casefold() not in used:
                    used.add(embedded_key.casefold())
                else:
                    # Repeated or missing key: a unique generated one instead
                    new_key = _generate_cite_key(
                        _get_first_author_last_name(pub), pub.get("year", ""), used
                    )
                    bibtex_str = _set_cite_key(bibtex_str, new_key)

                entries.append(_normalize_embedded_bibtex(bibtex_str))
                stats["embedded"] += 1
                continue

        # Fallback: generate from extracted fields
        last_name = _get_first_author_last_name(pub)
        cite_key = _generate_cite_key(last_name, pub.get("year", ""), used)
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
