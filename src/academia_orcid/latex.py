"""LaTeX generation for ORCID publication and data sections."""

# Escaping is the vendored coe_core.latex (latex_text.py; refreshed from
# coe-data-core with `just vendor-set`), shared with the twin repo:
# - escape_latex (= escape_latex_lossy) for structured fields (names, venues,
#   organizations): specials escaped, and characters pdflatex cannot set with the
#   report preamble dropped, while dashes, quotes and letters such as ł, ć and š
#   are kept (audit SCH-07);
# - escape_latex_smart (normalize.py, = markup_to_latex) for free text that may
#   carry HTML tags or $...$ math (titles, biography).
from academia_orcid.latex_text import escape_latex_lossy as escape_latex
from academia_orcid.latex_text import sanitize_url_for_latex

__all__ = ["escape_latex", "sanitize_url_for_latex"]


def format_date_range(start_year: str, end_year: str) -> str:
    """Format a date range for display."""
    if start_year and end_year:
        return f"{start_year}--{end_year}"
    elif start_year:
        return f"{start_year}--present"
    elif end_year:
        return end_year
    return ""


def _generate_publication_list(lines: list[str], subsection_name: str, publications: list[dict]):
    """Generate a LaTeX itemize list for a category of publications."""
    from academia_orcid.normalize import escape_latex_smart

    lines.append(f"\\subsection{{{subsection_name}}}")
    lines.append(r"\begin{raggedright}")
    lines.append(r"\begin{itemize}")
    for pub in publications:
        year = escape_latex(pub.get("year", ""))
        authors = escape_latex(pub.get("authors", ""))
        title = escape_latex_smart(pub.get("title", ""))
        venue = escape_latex(pub.get("venue", ""))
        doi = pub.get("doi", "")

        entry = f"{year}: "
        if authors:
            entry += f"{authors}, "
        entry += f"``{title}.''"
        if venue:
            entry += f" \\textit{{{venue}}}."

        # Add DOI link if available (on new line, lowercase)
        if doi:
            doi_escaped = escape_latex(doi).lower()
            doi_url = sanitize_url_for_latex(f"https://doi.org/{doi}".lower())
            if doi_url:
                entry += f"\\\\ \\href{{{doi_url}}}{{DOI:{doi_escaped}}}"
            else:
                entry += f"\\\\ DOI:{doi_escaped}"

        lines.append(f"  \\item {entry}")
    lines.append(r"\end{itemize}")
    lines.append(r"\end{raggedright}")
    lines.append("")


def _orcid_link(lines: list[str], orcid_id: str) -> None:
    """The "ORCID: <id>" line linking the profile (URL sanitized, defense in depth)."""
    orcid_url = sanitize_url_for_latex(f"https://orcid.org/{orcid_id}")
    orcid_id_escaped = escape_latex(orcid_id)
    lines.append(r"\noindent")
    if orcid_url:
        lines.append(f"ORCID: \\href{{{orcid_url}}}{{{orcid_id_escaped}}}")
    else:
        lines.append(f"ORCID: {orcid_id_escaped}")
    lines.append("")


def generate_latex_summary(
    orcid_id: str, journal_articles: list, conference_papers: list, other_publications: list
) -> str:
    """The publications summary: ORCID profile link and counts by type.

    Written to orcid-publications-summary.tex, which the composer template inputs
    under its own "ORCID Publications" heading (audit ORC-03). The report header
    already names the period, so the counts are plain.
    """
    lines: list[str] = []
    _orcid_link(lines, orcid_id)
    counts = [
        f"{label}: {len(pubs)}"
        for label, pubs in (
            ("Journal Articles", journal_articles),
            ("Conference Papers", conference_papers),
            ("Other Publications", other_publications),
        )
        if pubs
    ]
    if counts:
        lines.append(r"\noindent")
        lines.append("\\\\\n".join(counts))
        lines.append("")
    return "\n".join(lines)


def generate_latex(
    orcid_id: str, journal_articles: list, conference_papers: list, other_publications: list
) -> str:
    """The publication lists, one subsection per type, with DOI links.

    No section heading, profile link or counts: the composer template writes the
    heading (fragments never emit ``\\section``; audit ORC-03) and the summary
    file (``generate_latex_summary``) carries the link and counts. Empty when
    there are no publications (no file; section contract rule 5).
    """
    if not journal_articles and not conference_papers and not other_publications:
        return ""

    lines: list[str] = []
    if journal_articles:
        _generate_publication_list(lines, "Journal Articles", journal_articles)

    if conference_papers:
        _generate_publication_list(lines, "Conference Papers", conference_papers)

    if other_publications:
        _generate_publication_list(lines, "Other Publications", other_publications)

    return "\n".join(lines)


def generate_data_latex(
    orcid_id: str,
    biography: str | None,
    external_identifiers: list[dict],
    fundings: list[dict],
    employments: list[dict],
    educations: list[dict],
    distinctions: list[dict],
    memberships: list[dict],
    services: list[dict],
) -> str:
    """The ORCID Data body (non-publication fields), one subsection per kind.

    Starts with the ORCID profile link; no section heading (the composer template
    writes it; audit ORC-03). Empty when no field has data.
    """
    lines: list[str] = []
    _orcid_link(lines, orcid_id)

    from academia_orcid.normalize import escape_latex_smart

    has_content = False

    # Biography (may contain HTML markup)
    if biography:
        has_content = True
        lines.append(r"\subsection{Biography}")
        lines.append(escape_latex_smart(biography))
        lines.append("")

    # Employments
    if employments:
        has_content = True
        lines.append(r"\subsection{Employment}")
        lines.append(r"\begin{itemize}")
        for emp in employments:
            role = escape_latex(emp.get("role", ""))
            dept = escape_latex(emp.get("department", ""))
            org = escape_latex(emp.get("organization", ""))
            location = escape_latex(emp.get("location", ""))
            date_range = format_date_range(emp.get("start_year", ""), emp.get("end_year", ""))

            entry = ""
            if role:
                entry += role
            if dept:
                entry += f", {dept}" if entry else dept
            if org:
                entry += f", {org}" if entry else org
            if location:
                entry += f" ({location})" if entry else location
            if date_range:
                entry += f", {date_range}" if entry else date_range

            lines.append(f"  \\item {entry}")
        lines.append(r"\end{itemize}")
        lines.append("")

    # Educations
    if educations:
        has_content = True
        lines.append(r"\subsection{Education}")
        lines.append(r"\begin{itemize}")
        for edu in educations:
            role = escape_latex(edu.get("role", ""))  # Degree
            dept = escape_latex(edu.get("department", ""))  # Field of study
            org = escape_latex(edu.get("organization", ""))
            location = escape_latex(edu.get("location", ""))
            date_range = format_date_range(edu.get("start_year", ""), edu.get("end_year", ""))

            entry = ""
            if role:
                entry += role
            if dept:
                entry += f" in {dept}" if entry else dept
            if org:
                entry += f", {org}" if entry else org
            if location:
                entry += f" ({location})" if entry else location
            if date_range:
                entry += f", {date_range}" if entry else date_range

            lines.append(f"  \\item {entry}")
        lines.append(r"\end{itemize}")
        lines.append("")

    # Fundings (labeled as Selected Projects)
    if fundings:
        has_content = True
        lines.append(r"\subsection{Selected Projects}")
        lines.append(r"\begin{itemize}")
        for funding in fundings:
            title = escape_latex_smart(funding.get("title", ""))
            org = escape_latex(funding.get("organization", ""))
            funding_type = escape_latex(funding.get("type", ""))
            date_range = format_date_range(
                funding.get("start_year", ""), funding.get("end_year", "")
            )

            entry = ""
            if title:
                entry += f"``{title}''"
            if org:
                entry += f", {org}" if entry else org
            if funding_type:
                entry += f" ({funding_type})" if entry else funding_type
            if date_range:
                entry += f", {date_range}" if entry else date_range

            lines.append(f"  \\item {entry}")
        lines.append(r"\end{itemize}")
        lines.append("")

    # External Identifiers
    if external_identifiers:
        has_content = True
        lines.append(r"\subsection{External Identifiers}")
        lines.append(r"\begin{itemize}")
        for ext_id in external_identifiers:
            id_type = escape_latex(ext_id.get("type", ""))
            id_value = escape_latex(ext_id.get("value", ""))
            url = sanitize_url_for_latex(ext_id.get("url", ""))

            if url:
                lines.append(f"  \\item {id_type}: \\href{{{url}}}{{{id_value}}}")
            else:
                lines.append(f"  \\item {id_type}: {id_value}")
        lines.append(r"\end{itemize}")
        lines.append("")

    # Distinctions/Awards
    if distinctions:
        has_content = True
        lines.append(r"\subsection{Distinctions}")
        lines.append(r"\begin{itemize}")
        for dist in distinctions:
            role = escape_latex(dist.get("role", ""))  # Award name
            org = escape_latex(dist.get("organization", ""))
            date_range = format_date_range(dist.get("start_year", ""), dist.get("end_year", ""))

            entry = ""
            if role:
                entry += role
            if org:
                entry += f", {org}" if entry else org
            if date_range:
                entry += f", {date_range}" if entry else date_range

            lines.append(f"  \\item {entry}")
        lines.append(r"\end{itemize}")
        lines.append("")

    # Memberships
    if memberships:
        has_content = True
        lines.append(r"\subsection{Memberships}")
        lines.append(r"\begin{itemize}")
        for mem in memberships:
            role = escape_latex(mem.get("role", ""))
            org = escape_latex(mem.get("organization", ""))
            date_range = format_date_range(mem.get("start_year", ""), mem.get("end_year", ""))

            entry = ""
            if org:
                entry += org
            if role:
                entry += f" -- {role}" if entry else role
            if date_range:
                entry += f", {date_range}" if entry else date_range

            lines.append(f"  \\item {entry}")
        lines.append(r"\end{itemize}")
        lines.append("")

    # Services
    if services:
        has_content = True
        lines.append(r"\subsection{External Service}")
        lines.append(r"\begin{itemize}")
        for svc in services:
            role = escape_latex(svc.get("role", ""))
            org = escape_latex(svc.get("organization", ""))
            date_range = format_date_range(svc.get("start_year", ""), svc.get("end_year", ""))

            entry = ""
            if role:
                entry += role
            if org:
                entry += f", {org}" if entry else org
            if date_range:
                entry += f", {date_range}" if entry else date_range

            lines.append(f"  \\item {entry}")
        lines.append(r"\end{itemize}")
        lines.append("")

    if not has_content:
        return ""  # no data: the caller writes no file (section contract rule 5; ORC-04)

    return "\n".join(lines)
