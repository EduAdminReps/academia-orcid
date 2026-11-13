# Vendored copy of coe-data-core/src/coe_core/latex.py -- do not edit here.
# Refresh from coe-data-core with: just vendor-set
"""LaTeX utilities: escaping, and HTML-marked text from outside sources.

Standard library only and importing nothing from coe_core: tamu-scholars and
academia-orcid deploy on their own, so coe-data-core copies this module
verbatim into each of them (``just vendor-set``, as ``latex_text.py``), and
``tests/test_vendored_drift.py`` fails if a copy differs. Change it here only.

- ``escape_latex``: our own data (en.db). Escapes the specials and maps what
  pdflatex cannot set; anything else unexpected fails the build, loudly.
- ``escape_latex_lossy``: text from outside (publication records). The same,
  then drops every character pdflatex cannot set, rather than fail.
- ``markup_to_latex``: titles and abstracts with HTML tags and ``$...$`` math.
- ``strip_html_tags``, ``clean_for_plaintext``: the same text for JSON/Word.
- ``sanitize_url_for_latex``: a URL safe inside ``\\href``.
"""

import html
import re
import unicodedata

# Every LaTeX special character and its text-mode replacement. Applied in a
# single pass (str.translate), so a replacement is never itself re-escaped:
# chained str.replace calls turned "\" into "\textbackslash{}" and then escaped
# its braces, rendering "x\y" as "x\{}y".
_LATEX_SPECIALS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

# Unicode characters pdflatex cannot typeset with the reports' preamble
# (T1 fontenc + utf8 inputenc + lmodern): each is a fatal "Unicode character
# ... not set up for use with LaTeX" error. Probed 2026-10-17 against the
# characters found in en.db text: curly quotes, dashes, ™, ℃ and the f-ligatures
# are fine; Greek, sub/superscripts, U+2212 and Word Symbol-font code points
# are not. Anything else non-Latin still fails loudly, as it should.
_GREEK = {
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta", "ε": r"\epsilon",
    "ζ": r"\zeta", "η": r"\eta", "θ": r"\theta", "ι": r"\iota", "κ": r"\kappa",
    "λ": r"\lambda", "μ": r"\mu", "ν": r"\nu", "ξ": r"\xi", "π": r"\pi",
    "ρ": r"\rho", "ς": r"\varsigma", "σ": r"\sigma", "τ": r"\tau", "υ": r"\upsilon",
    "φ": r"\phi", "χ": r"\chi", "ψ": r"\psi", "ω": r"\omega", "ϑ": r"\vartheta",
    "ϕ": r"\phi", "ϖ": r"\varpi", "Γ": r"\Gamma", "Δ": r"\Delta", "Θ": r"\Theta",
    "Λ": r"\Lambda", "Ξ": r"\Xi", "Π": r"\Pi", "Σ": r"\Sigma", "Υ": r"\Upsilon",
    "Φ": r"\Phi", "Ψ": r"\Psi", "Ω": r"\Omega",
}  # fmt: skip
# Greek letters drawn like Latin ones have no LaTeX macro.
_GREEK_AS_LATIN = {
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K",
    "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Χ": "X", "ο": "o",
}  # fmt: skip
# Word's Symbol font stores Greek in the private-use area at U+F000 + the ASCII
# letter it sits on: U+F062 ('b') is β, U+F06D ('m') is μ.
_SYMBOL_FONT = dict(
    zip(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "αβχδεφγηιϕκλμνοπθρστυϖωξψζΑΒΧΔΕΦΓΗΙϑΚΛΜΝΟΠΘΡΣΤΥςΩΞΨΖ",
        strict=True,
    )
)


def _unicode_fallbacks() -> dict[str, str]:
    table = {ch: rf"\ensuremath{{{macro}}}" for ch, macro in _GREEK.items()}
    table.update(_GREEK_AS_LATIN)
    for ascii_letter, greek in _SYMBOL_FONT.items():
        table[chr(0xF000 + ord(ascii_letter))] = table[greek]
    for digit in range(10):
        table[chr(0x2080 + digit)] = rf"\textsubscript{{{digit}}}"
    for code, numeral in zip((0x2070, *range(0x2074, 0x207A)), "0456789", strict=True):
        table[chr(code)] = rf"\textsuperscript{{{numeral}}}"
    table.update({
        "⁺": r"\textsuperscript{+}", "⁻": r"\textsuperscript{-}",
        "₊": r"\textsubscript{+}", "₋": r"\textsubscript{-}",
        "−": r"\ensuremath{-}",
    })  # fmt: skip
    table.update(_MATH_SYMBOLS)
    return table


# Symbols and spaces pdflatex cannot set as text, but base LaTeX (no amssymb)
# has a macro for. Probed 2026-11-12 over the ORCID and Scholars caches, where
# U+22xx alone occurs about 2,400 times.
_MATH_SYMBOLS = {
    "∼": r"\ensuremath{\sim}", "≈": r"\ensuremath{\approx}", "≤": r"\ensuremath{\leq}",
    "≥": r"\ensuremath{\geq}", "∗": r"\ensuremath{\ast}", "∞": r"\ensuremath{\infty}",
    "∈": r"\ensuremath{\in}", "⋅": r"\ensuremath{\cdot}", "√": r"\ensuremath{\surd}",
    "∆": r"\ensuremath{\Delta}", "∘": r"\ensuremath{\circ}", "∙": r"\ensuremath{\bullet}",
    "∥": r"\ensuremath{\parallel}", "⇌": r"\ensuremath{\rightleftharpoons}",
    "ɛ": r"\ensuremath{\varepsilon}", "′": r"\ensuremath{'}", "″": r"\ensuremath{''}",
    "∕": "/", "\u2009": r"\,", "\u202f": r"\,",
}  # fmt: skip


_LATEX_TRANSLATION = str.maketrans({**_unicode_fallbacks(), **_LATEX_SPECIALS})


def escape_latex(text: object) -> str:
    """Escape the 10 LaTeX special characters in text, and map the Unicode
    characters pdflatex cannot typeset (Greek, sub/superscripts, minus, Word
    Symbol-font letters) to LaTeX.

    None becomes ""; any other non-string is converted with str() first, then
    escaped.
    """
    if text is None:
        return ""
    return str(text).translate(_LATEX_TRANSLATION)


# ── Text from outside sources ────────────────────────────────────────────

# What pdflatex sets as text with the reports' preamble (T1 + utf8 inputenc +
# lmodern), probed 2026-11-12 over every character in the ORCID and Scholars
# caches: printable ASCII and Latin-1, Latin Extended-A except U+0127 (ħ), and
# the code points below (dashes, quotes, †, •, …, ‰, €, ™, ℃, arrows, ligatures).
_RENDERABLE_EXTRA = frozenset(
    chr(c)
    for c in (
        0x0192, 0x01D0, 0x01D2, 0x01E6, 0x01E7, 0x0218, 0x0219, 0x021B, 0x02C6, 0x02C7,
        0x02D9, 0x02DC, 0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2016, 0x2018,
        0x2019, 0x201A, 0x201C, 0x201D, 0x201E, 0x2020, 0x2021, 0x2022, 0x2026, 0x2030,
        0x2044, 0x204E, 0x20AC, 0x2103, 0x2122, 0x2190, 0x2192, 0x2423, 0x25E6, 0x27E8,
        0x27E9, 0x3008, 0x3009, 0xFB01, 0xFB02,
    )
)  # fmt: skip


def _settable(ch: str) -> bool:
    """True if pdflatex sets ``ch`` with the reports' preamble, or escape_latex maps it."""
    code = ord(ch)
    return (
        ch in "\t\n\r"
        or 0x20 <= code < 0x7F
        or (0xA0 <= code <= 0xFF and code != 0xAD)
        or (0x100 <= code <= 0x17F and code != 0x127)
        or ch in _RENDERABLE_EXTRA
        or code in _LATEX_TRANSLATION
    )


def _drop_unsettable(text: str) -> str:
    """NFC-normalize (a letter plus a combining accent becomes one letter), then
    drop every character pdflatex cannot set: other scripts, controls, soft hyphens."""
    return "".join(ch for ch in unicodedata.normalize("NFC", text) if _settable(ch))


def escape_latex_lossy(text: object) -> str:
    """``escape_latex`` for text from outside sources: characters pdflatex cannot
    set (Cyrillic, Arabic, CJK, most math symbols) are dropped instead of failing
    the build. Dashes, quotes and Latin letters such as ł, ć and š are kept."""
    if text is None:
        return ""
    return escape_latex(_drop_unsettable(str(text)))


_MARKUP_COMMANDS = {
    "sub": r"\textsubscript", "inf": r"\textsubscript", "sup": r"\textsuperscript",
    "i": r"\textit", "em": r"\textit", "b": r"\textbf", "strong": r"\textbf",
    "scp": r"\textsc",
}  # fmt: skip
_HTML_TAG_RE = re.compile(r"</?(?:mml:)?[a-zA-Z][^>]*>", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")
# One token at a time: an inline math region (not after a backslash), a known
# tag, or any other tag. Text between tokens is plain.
_MARKUP_TOKEN_RE = re.compile(
    r"(?P<math>(?<!\\)\$[^$]+\$)"
    r"|<(?P<close>/?)(?P<tag>sub|inf|sup|i|em|b|strong|scp)\s*>"
    r"|(?P<other></?(?:mml:)?[a-zA-Z][^>]*>)",
    re.IGNORECASE,
)
# Math is kept for pdflatex as written, but only with characters it can set:
# Greek and the like mapped, the rest dropped. (The ten specials are LaTeX here.)
_MATH_TRANSLATION = str.maketrans(_unicode_fallbacks())

# Math macros base LaTeX defines; the reports' preamble loads neither amsmath
# nor amssymb, so math using anything else is shown as text instead.
_BASE_MATH = frozenset(
    """alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa
    lambda mu nu xi pi varpi rho varrho sigma varsigma tau upsilon phi varphi chi psi
    omega Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega times cdot pm mp
    div ast star circ bullet cap cup wedge vee oplus otimes leq le geq ge neq ne ll gg
    sim simeq approx equiv propto parallel perp in ni subset supset subseteq supseteq
    notin leftarrow rightarrow leftrightarrow Leftarrow Rightarrow Leftrightarrow
    uparrow downarrow to gets mapsto longrightarrow rightleftharpoons infty partial
    nabla prime ell hbar Re Im aleph emptyset forall exists neg surd angle triangle
    backslash sum prod int oint log ln exp sin cos tan sinh cosh tanh lim max min sup
    inf det arg dim frac sqrt mathrm mathit mathbf mathsf mathtt mathcal rm it bf left
    right big Big bigl bigr hat bar tilde vec dot ddot check breve acute grave
    overline underline overbrace underbrace widehat widetilde ldots cdots vdots ddots
    langle rangle lfloor rfloor lceil rceil quad qquad""".split()  # noqa: SIM905 (a word list reads better)
)
# Publisher macros with an obvious base-LaTeX meaning (seen in the caches).
_MATH_REPAIRS = {
    r"\less": "<", r"\greater": ">", r"\mathsemicolon": ";", r"\mathplus": "+",
    r"\mathcolon": ":", r"\text": r"\mathrm",
}  # fmt: skip
_CONTROL_WORD_RE = re.compile(r"\\([a-zA-Z]+)")
# A run of sub/superscripts on one base; each kind may appear once in a run.
_SCRIPT_RUN_RE = re.compile(r"(?:[_^]\s*(?:\{[^{}]*\}|\\[a-zA-Z]+|[^\s{}\\_^]))+")
_EMPTY_SCRIPT_RE = re.compile(r"[_^]\s*(?:$|[}_^])")


def _repair_math(math: str) -> str:
    """Entities and tags out, upgreek and publisher macros to base LaTeX."""
    math = _HTML_TAG_RE.sub("", html.unescape(math))
    math = re.sub(r"\\up([a-zA-Z]+)", lambda m: "\\" + m[1] if m[1] in _BASE_MATH else m[0], math)
    math = re.sub(r"\\mathrm([A-Z][a-zA-Z]*)", r"\\mathrm{\1}", math)
    return _CONTROL_WORD_RE.sub(lambda m: _MATH_REPAIRS.get(m[0], m[0]), math)


def _safe_math(body: str) -> bool:
    """True if pdflatex can set ``$body$`` with base LaTeX: braces balance, no
    alignment or comment characters, no double sub/superscript, only known macros."""
    depth = 0
    for i, ch in enumerate(body):
        if body[i - 1 : i] == "\\":
            continue
        if ch in "&#%":
            return False
        depth += {"{": 1, "}": -1}.get(ch, 0)
        if depth < 0:
            return False
    if depth or _EMPTY_SCRIPT_RE.search(body):
        return False
    for run in _SCRIPT_RUN_RE.findall(body):
        kinds = re.findall(r"[_^](?![^{]*\})", run)
        if kinds.count("_") > 1 or kinds.count("^") > 1:
            return False
    return all(word in _BASE_MATH for word in _CONTROL_WORD_RE.findall(body))


def _plain_to_latex(text: str) -> str:
    """Plain text between tokens: escaped, keeping LaTeX's backslash-space."""
    return "\\ ".join(escape_latex_lossy(part) for part in text.split("\\ "))


def markup_to_latex(text: object) -> str:
    """LaTeX for a title or abstract that carries HTML tags and ``$...$`` math.

    <i>/<em>, <b>/<strong>, <sub>/<inf>, <sup> and <scp> become \\textit and
    friends, with their content escaped like the rest; nesting is kept with a
    stack, an unmatched closing tag is ignored and every tag left open is closed
    at the end, so the braces always balance. Other tags (MathML, <p>, ...) are
    dropped. ``$$...$$`` becomes inline math. Math is repaired (entities, tags,
    upgreek and publisher macros) and passed through if base LaTeX can set it,
    else shown as text. Characters pdflatex cannot set are dropped.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFC", str(text))
    text = re.sub(r"\$\$([^$]+)\$\$", r"$\1$", text)
    out: list[str] = []
    open_tags: list[str] = []
    pos = 0
    for match in _MARKUP_TOKEN_RE.finditer(text):
        out.append(_plain_to_latex(text[pos : match.start()]))
        pos = match.end()
        if match["math"]:
            body = _drop_unsettable(_repair_math(match["math"][1:-1]))
            if body.strip() and _safe_math(body):
                out.append("$" + body.translate(_MATH_TRANSLATION) + "$")
            else:  # not math base LaTeX can set: show the source as text
                out.append(_plain_to_latex(body))
        elif match["tag"]:
            tag = match["tag"].lower()
            if not match["close"]:
                out.append(_MARKUP_COMMANDS[tag] + "{")
                open_tags.append(tag)
            elif open_tags:
                out.append("}")
                open_tags.pop()
    out.append(_plain_to_latex(text[pos:]))
    out.append("}" * len(open_tags))
    return _WHITESPACE_RE.sub(" ", "".join(out)).strip()


def strip_html_tags(text: str) -> str:
    """Remove all HTML/XML tags, keeping their content; collapse whitespace."""
    if not text or "<" not in text:
        return text
    return _WHITESPACE_RE.sub(" ", _HTML_TAG_RE.sub("", text)).strip()


_SUB_MAP = str.maketrans("0123456789+-=()aehijklmnoprstuvx", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ")
_SUP_MAP = str.maketrans("0123456789+-=()ni", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ")
_SUB_TAG_RE = re.compile(r"<(?:sub|inf)>(.*?)</(?:sub|inf)>", re.IGNORECASE | re.DOTALL)
_SUP_TAG_RE = re.compile(r"<sup>(.*?)</sup>", re.IGNORECASE | re.DOTALL)


def clean_for_plaintext(text: str) -> str:
    """Plain text for JSON/Word: <sub>/<sup> as Unicode sub/superscripts where
    possible, other tags dropped, ``$`` math delimiters dropped (content kept)."""
    if not text:
        return text
    text = _SUB_TAG_RE.sub(lambda m: m.group(1).translate(_SUB_MAP), text)
    text = _SUP_TAG_RE.sub(lambda m: m.group(1).translate(_SUP_MAP), text)
    text = strip_html_tags(text)
    text = text.replace("$$", "").replace("$", "")
    return _WHITESPACE_RE.sub(" ", text).strip()


def sanitize_url_for_latex(url: str) -> str:
    """A URL safe inside ``\\href{}{}``: http(s) only, no backslash or brace; else ""."""
    if not url:
        return ""
    url = url.strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        return ""
    return url.replace("\\", "").replace("{", "").replace("}", "")
