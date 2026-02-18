"""Tests for academia_orcid.latex module."""

from academia_orcid.latex import (
    escape_latex,
    format_date_range,
    generate_data_latex,
    generate_latex,
    sanitize_url_for_latex,
)


# ── escape_latex ───────────────────────────────────────────────────────────


def test_escape_latex_ampersand():
    assert escape_latex("A&M") == r"A\&M"


def test_escape_latex_multiple():
    result = escape_latex("100% of $5 #1")
    assert r"\%" in result
    assert r"\$" in result
    assert r"\#" in result


def test_escape_latex_empty():
    assert escape_latex("") == ""


# ── format_date_range ──────────────────────────────────────────────────────


def test_format_date_range_both():
    assert format_date_range("2020", "2025") == "2020--2025"


def test_format_date_range_start_only():
    assert format_date_range("2020", "") == "2020--present"


def test_format_date_range_empty():
    assert format_date_range("", "") == ""


# ── generate_latex (publications) ──────────────────────────────────────────


def test_generate_latex_publications():
    journals = [{"year": "2024", "authors": "Smith, A.", "title": "Test Paper",
                 "venue": "IEEE TSP", "doi": "10.1109/test"}]
    conferences = [{"year": "2023", "authors": "Jones, B.", "title": "Conf Paper",
                    "venue": "ICASSP", "doi": ""}]
    result = generate_latex("0000-0001-2345-6789", journals, conferences, [])

    assert r"\section{ORCID Publications}" in result
    assert r"\subsection{Journal Articles}" in result
    assert r"\subsection{Conference Papers}" in result
    assert "0000-0001-2345-6789" in result
    assert "10.1109/test" in result


def test_generate_latex_empty():
    result = generate_latex("0000-0001-2345-6789", [], [], [])
    assert result == ""


# ── generate_data_latex ────────────────────────────────────────────────────


def test_generate_data_latex_sections():
    result = generate_data_latex(
        orcid_id="0000-0001-2345-6789",
        biography="A researcher.",
        external_identifiers=[{"type": "Scopus", "value": "123", "url": ""}],
        fundings=[{"title": "Grant", "organization": "NSF", "type": "grant",
                   "start_year": "2022", "end_year": "2025"}],
        employments=[{"role": "Prof", "department": "ECE", "organization": "TAMU",
                      "location": "TX", "start_year": "2020", "end_year": ""}],
        educations=[],
        distinctions=[],
        memberships=[{"role": "Member", "organization": "IEEE",
                      "start_year": "2018", "end_year": "", "location": "",
                      "department": ""}],
        services=[],
    )

    assert r"\section{ORCID Data}" in result
    assert r"\subsection{Biography}" in result
    assert r"\subsection{Employment}" in result
    assert r"\subsection{Selected Projects}" in result
    assert r"\subsection{Memberships}" in result
    assert r"\subsection{External Identifiers}" in result
    # Sections with no data should NOT appear
    assert r"\subsection{Education}" not in result
    assert r"\subsection{Distinctions}" not in result
    assert r"\subsection{External Service}" not in result


def test_generate_data_latex_empty():
    result = generate_data_latex(
        orcid_id="0000-0001-2345-6789",
        biography=None,
        external_identifiers=[],
        fundings=[],
        employments=[],
        educations=[],
        distinctions=[],
        memberships=[],
        services=[],
    )
    assert "No additional data found" in result


# ── SECURITY: sanitize_url_for_latex ──────────────────────────────────────


def test_sanitize_url_valid_https():
    assert sanitize_url_for_latex("https://doi.org/10.1109/test") == "https://doi.org/10.1109/test"


def test_sanitize_url_valid_http():
    assert sanitize_url_for_latex("http://example.com") == "http://example.com"


def test_sanitize_url_rejects_non_http():
    assert sanitize_url_for_latex("ftp://evil.com/file") == ""
    assert sanitize_url_for_latex("javascript:alert(1)") == ""
    assert sanitize_url_for_latex("file:///etc/passwd") == ""


def test_sanitize_url_strips_braces():
    """Braces in URLs could break \\href{}{} syntax."""
    assert sanitize_url_for_latex("https://example.com/{test}") == "https://example.com/test"


def test_sanitize_url_strips_backslashes():
    """Backslashes in URLs could inject LaTeX commands."""
    assert sanitize_url_for_latex("https://example.com/\\input{evil}") == "https://example.com/inputevil"


def test_sanitize_url_empty():
    assert sanitize_url_for_latex("") == ""
    assert sanitize_url_for_latex(None) == ""


def test_sanitize_url_injection_attempt():
    """Test that a URL designed to break out of \\href is neutralized."""
    malicious = "https://evil.com/}\\input{/etc/passwd}"
    result = sanitize_url_for_latex(malicious)
    assert "\\" not in result
    assert "{" not in result
    assert "}" not in result


# ── SECURITY: external identifier URLs are sanitized ──────────────────────


def test_generate_data_latex_sanitizes_ext_id_url():
    """External identifier URLs with injection payloads should be sanitized."""
    result = generate_data_latex(
        orcid_id="0000-0001-2345-6789",
        biography=None,
        external_identifiers=[{
            "type": "Scopus",
            "value": "12345",
            "url": "https://scopus.com/}\\input{evil}",
        }],
        fundings=[], employments=[], educations=[],
        distinctions=[], memberships=[], services=[],
    )
    # The URL should be sanitized - no raw backslash or braces from the URL
    assert "\\input" not in result or "\\href{https://scopus.com/inputevil}" in result


def test_generate_data_latex_rejects_non_http_ext_id():
    """Non-HTTP external identifier URLs should fall back to text-only."""
    result = generate_data_latex(
        orcid_id="0000-0001-2345-6789",
        biography=None,
        external_identifiers=[{
            "type": "Scopus",
            "value": "12345",
            "url": "javascript:alert(1)",
        }],
        fundings=[], employments=[], educations=[],
        distinctions=[], memberships=[], services=[],
    )
    # The ORCID profile \href is always present; check the ext_id line specifically
    assert "\\item Scopus: 12345" in result
    assert "javascript" not in result
