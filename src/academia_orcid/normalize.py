"""Text normalization for ORCID data fields.

Handles two real-world problems in ORCID records:
1. HTML markup in text fields (<i>, <sub>, <sup>, <inf>, <scp>, <mml:*>)
2. Embedded LaTeX math sequences ($...$, $$...$$)

Functions are organized by output format:
- strip_html_tags()     -- format-agnostic: remove all HTML, keep text
- html_to_latex()       -- LaTeX output: convert HTML tags to LaTeX commands
- escape_latex_smart()  -- LaTeX output: full pipeline (HTML + math-aware escaping)
- clean_for_plaintext() -- JSON/DOCX output: strip HTML, Unicode sub/superscripts
"""

import re

from academia_orcid.latex import _NON_LATIN1_RE, escape_latex


# ── Shared patterns ──────────────────────────────────────────────────────

# Matches any HTML/XML tag, including namespace prefixes like mml:
_HTML_TAG_RE = re.compile(r'</?(?:mml:)?[a-zA-Z][^>]*>', re.IGNORECASE)
_WHITESPACE_COLLAPSE_RE = re.compile(r'\s+')


# ── Format-agnostic ─────────────────────────────────────────────────────

def strip_html_tags(text: str) -> str:
    """Remove all HTML/XML tags from text, preserving inner content."""
    if not text or '<' not in text:
        return text
    result = _HTML_TAG_RE.sub('', text)
    result = _WHITESPACE_COLLAPSE_RE.sub(' ', result).strip()
    return result


# ── LaTeX output ─────────────────────────────────────────────────────────

# Known HTML tags → LaTeX command conversions (order: inner tags first)
_HTML_TO_LATEX_MAP = [
    # Subscript: <sub>...</sub> and <inf>...</inf> (Elsevier non-standard)
    (re.compile(r'<(?:sub|inf)>(.*?)</(?:sub|inf)>', re.IGNORECASE | re.DOTALL),
     r'\\textsubscript{\1}'),
    # Superscript: <sup>...</sup>
    (re.compile(r'<sup>(.*?)</sup>', re.IGNORECASE | re.DOTALL),
     r'\\textsuperscript{\1}'),
    # Italic: <i>...</i> and <em>...</em>
    (re.compile(r'<(?:i|em)>(.*?)</(?:i|em)>', re.IGNORECASE | re.DOTALL),
     r'\\textit{\1}'),
    # Bold: <b>...</b> and <strong>...</strong>
    (re.compile(r'<(?:b|strong)>(.*?)</(?:b|strong)>', re.IGNORECASE | re.DOTALL),
     r'\\textbf{\1}'),
    # Small caps: <scp>...</scp> (Wiley style)
    (re.compile(r'<scp>(.*?)</scp>', re.IGNORECASE | re.DOTALL),
     r'\\textsc{\1}'),
]

# Matches LaTeX commands inserted by html_to_latex so we can protect them
_LATEX_CMD_RE = re.compile(
    r'(\\(?:textit|textbf|textsubscript|textsuperscript|textsc)\{[^}]*\})'
)


def html_to_latex(text: str) -> str:
    """Convert known HTML tags to LaTeX equivalents.

    Handles: <i>, <em>, <b>, <strong>, <sub>, <inf>, <sup>, <scp>.
    Strips remaining unrecognized tags (MathML, <title>, <p>, <br>, etc.).
    """
    if not text or '<' not in text:
        return text
    for pattern, replacement in _HTML_TO_LATEX_MAP:
        text = pattern.sub(replacement, text)
    # Strip any remaining tags
    text = _HTML_TAG_RE.sub('', text)
    text = _WHITESPACE_COLLAPSE_RE.sub(' ', text).strip()
    return text


def _split_math_regions(text: str) -> list[tuple[bool, str]]:
    """Split text into math and non-math regions.

    Math regions are delimited by balanced $...$ pairs.
    Returns list of (is_math, content) tuples.
    """
    # Match $...$ (non-greedy, no nested $)
    parts = []
    last_end = 0

    for m in re.finditer(r'\$[^$]+\$', text):
        # Add non-math text before this match
        if m.start() > last_end:
            parts.append((False, text[last_end:m.start()]))
        parts.append((True, m.group()))
        last_end = m.end()

    # Add remaining non-math text
    if last_end < len(text):
        parts.append((False, text[last_end:]))

    if not parts:
        parts.append((False, text))

    return parts


def _escape_preserving_commands(text: str) -> str:
    """Escape LaTeX special chars but preserve LaTeX commands from html_to_latex."""
    parts = _LATEX_CMD_RE.split(text)
    result = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            # Matched LaTeX command — pass through unchanged
            result.append(part)
        else:
            # Plain text — escape it
            result.append(escape_latex(part))
    return "".join(result)


def escape_latex_smart(text: str) -> str:
    """Escape text for LaTeX output, preserving math and converting HTML.

    Pipeline:
        1. Convert HTML tags to LaTeX commands
        2. Normalize $$...$$ to $...$
        3. Protect backslash-space sequences
        4. Split into math/non-math regions
        5. escape_latex() on non-math regions only (preserving LaTeX commands)
        6. Rejoin and restore protected sequences
    """
    if not text:
        return ""

    # Step 1: HTML → LaTeX
    text = html_to_latex(text)

    # Step 2: Normalize display math to inline (titles don't need display math)
    text = re.sub(r'\$\$([^$]+)\$\$', r'$\1$', text)

    # Step 3: Protect backslash-space (LaTeX spacing command)
    SENTINEL = "\x00BSSP\x00"
    text = text.replace("\\ ", SENTINEL)

    # Step 4–5: Split and escape non-math portions
    segments = _split_math_regions(text)
    parts = []
    for is_math, content in segments:
        if is_math:
            parts.append(content)
        else:
            parts.append(_escape_preserving_commands(content))

    result = "".join(parts)

    # Step 6: Restore backslash-space
    result = result.replace(SENTINEL, "\\ ")

    # Step 7: Strip non-Latin-1 characters (CJK, Arabic, etc.) that pdflatex
    # cannot render. This catches characters in math regions or anywhere
    # else that escape_latex() may not have processed.
    result = _NON_LATIN1_RE.sub('', result)
    return result


# ── Plaintext output (JSON, DOCX) ───────────────────────────────────────

_SUB_MAP = str.maketrans(
    '0123456789+-=()aehijklmnoprstuvx',
    '₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ',
)
_SUP_MAP = str.maketrans(
    '0123456789+-=()ni',
    '⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ',
)


def _to_unicode_sub(match: re.Match) -> str:
    content = match.group(1)
    translated = content.translate(_SUB_MAP)
    return translated


def _to_unicode_sup(match: re.Match) -> str:
    content = match.group(1)
    translated = content.translate(_SUP_MAP)
    return translated


def clean_for_plaintext(text: str) -> str:
    """Clean text for plain-text output (JSON, DOCX).

    - Converts <sub>/<inf> to Unicode subscripts where possible
    - Converts <sup> to Unicode superscripts where possible
    - Strips remaining HTML tags
    - Strips LaTeX math delimiters ($ signs), leaves content
    """
    if not text:
        return text

    # Convert sub/sup to Unicode before stripping tags
    text = re.sub(r'<(?:sub|inf)>(.*?)</(?:sub|inf)>', _to_unicode_sub,
                  text, flags=re.IGNORECASE)
    text = re.sub(r'<sup>(.*?)</sup>', _to_unicode_sup,
                  text, flags=re.IGNORECASE)

    # Strip remaining HTML
    text = strip_html_tags(text)

    # Strip LaTeX math delimiters but keep content
    text = text.replace('$$', '').replace('$', '')

    # Collapse whitespace
    text = _WHITESPACE_COLLAPSE_RE.sub(' ', text).strip()
    return text
