"""Tests for academia_orcid.normalize: the vendored coe_core.latex as this repo uses it.

The rules themselves are tested upstream (coe-data-core tests/test_latex.py); these
pin what the publication sections rely on, including the nested-tag titles that
used to break pdflatex (audit ORC-05 / SCH-01).
"""

from academia_orcid.normalize import (
    clean_for_plaintext,
    escape_latex_smart,
    strip_html_tags,
)

# ── strip_html_tags ──────────────────────────────────────────────────────


def test_strip_no_tags():
    assert strip_html_tags("plain text") == "plain text"


def test_strip_empty():
    assert strip_html_tags("") == ""


def test_strip_none():
    assert strip_html_tags(None) is None


def test_strip_italic():
    assert strip_html_tags("<i>in vitro</i>") == "in vitro"


def test_strip_subscript():
    assert strip_html_tags("CO<sub>2</sub>") == "CO2"


def test_strip_inf_tag():
    assert strip_html_tags("CO<inf>2</inf>") == "CO2"


def test_strip_superscript():
    assert strip_html_tags("Ni<sup>2+</sup>") == "Ni2+"


def test_strip_scp_tag():
    assert strip_html_tags("<scp>Computer-aided</scp>") == "Computer-aided"


def test_strip_title_wrapper():
    assert strip_html_tags("<title>Effect of X on Y</title>") == "Effect of X on Y"


def test_strip_mathml_namespace():
    text = '<mml:math xmlns:mml="http://www.w3.org/1998/Math/MathML"><mml:msub><mml:mn>3</mml:mn></mml:msub></mml:math>'
    result = strip_html_tags(text)
    assert '<' not in result
    assert '3' in result


def test_strip_collapses_whitespace():
    text = "<i>Escherichia coli</i>\n                    biofilms"
    result = strip_html_tags(text)
    assert "  " not in result


# ── tags (escape_latex_smart) ────────────────────────────────────────────────────────


def test_escape_latex_smart_italic():
    assert escape_latex_smart("<i>in vitro</i>") == r"\textit{in vitro}"


def test_escape_latex_smart_em():
    assert escape_latex_smart("<em>E. coli</em>") == r"\textit{E. coli}"


def test_escape_latex_smart_subscript():
    assert escape_latex_smart("CO<sub>2</sub>") == r"CO\textsubscript{2}"


def test_escape_latex_smart_inf():
    assert escape_latex_smart("CO<inf>2</inf>") == r"CO\textsubscript{2}"


def test_escape_latex_smart_superscript():
    assert escape_latex_smart("x<sup>2</sup>") == r"x\textsuperscript{2}"


def test_escape_latex_smart_scp():
    assert escape_latex_smart("<scp>PAAm</scp>") == r"\textsc{PAAm}"


def test_escape_latex_smart_bold():
    assert escape_latex_smart("<b>important</b>") == r"\textbf{important}"


def test_escape_latex_smart_strong():
    assert escape_latex_smart("<strong>key</strong>") == r"\textbf{key}"


def test_escape_latex_smart_remaining_stripped():
    result = escape_latex_smart('<mml:math>content</mml:math>')
    assert '<' not in result
    assert 'content' in result


def test_escape_latex_smart_no_tags():
    assert escape_latex_smart("plain text") == "plain text"


def test_escape_latex_smart_chemical_formula():
    text = "Mg<sub>2</sub>Si<sub>x</sub>Sn<sub>1-x</sub>"
    result = escape_latex_smart(text)
    assert r"\textsubscript{2}" in result
    assert r"\textsubscript{x}" in result
    assert r"\textsubscript{1-x}" in result


def test_escape_latex_smart_empty():
    assert escape_latex_smart("") == ""


def test_escape_latex_smart_none():
    assert escape_latex_smart(None) == ""


# ── nesting, specials inside tags, stray dollars (audit ORC-05 / SCH-01) ──


def test_nested_tags_keep_balanced_braces():
    assert escape_latex_smart("CO<i><sub>2</sub></i> capture") == (
        r"CO\textit{\textsubscript{2}} capture"
    )
    assert escape_latex_smart("<sub><i>x</i></sub> y") == r"\textsubscript{\textit{x}} y"


def test_specials_inside_tags_are_escaped():
    assert escape_latex_smart("<i>R&D_x</i> 50%") == r"\textit{R\&D\_x} 50\%"


def test_unclosed_and_stray_tags():
    assert escape_latex_smart("<i>open") == r"\textit{open}"
    assert escape_latex_smart("stray</i> close") == "stray close"


def test_lone_dollar_is_escaped():
    assert escape_latex_smart("price is $50") == r"price is \$50"


def test_braces_always_balance():
    for title in ["<i>a<sub>b</i>c</sub>", "<b><i>x</b>", "</sub></i>", "a <sup>2"]:
        latex = escape_latex_smart(title).replace(r"\{", "").replace(r"\}", "")
        assert latex.count("{") == latex.count("}"), title


# ── escape_latex_smart ───────────────────────────────────────────────────


def test_smart_plain_text():
    assert escape_latex_smart("A & B") == r"A \& B"


def test_smart_empty():
    assert escape_latex_smart("") == ""


def test_smart_preserves_inline_math():
    result = escape_latex_smart("$k$-means algorithm")
    assert "$k$" in result


def test_smart_html_subscript():
    result = escape_latex_smart("CO<sub>2</sub> emissions")
    assert r"\textsubscript{2}" in result
    assert '<' not in result


def test_smart_html_italic():
    result = escape_latex_smart("<i>in vitro</i> study")
    assert r"\textit{in vitro}" in result


def test_smart_special_chars_outside_math():
    result = escape_latex_smart("10% of $x$ in A&M")
    assert r"\%" in result
    assert r"\&" in result
    assert "$x$" in result


def test_smart_backslash_space():
    result = escape_latex_smart("vs.\\ Information")
    assert "\\ " in result


def test_smart_display_math_normalized():
    """$$...$$ should be normalized to $...$."""
    result = escape_latex_smart("$$\\tau$$-lepton")
    assert "$\\tau$" in result
    assert "$$" not in result


def test_smart_chemical_with_math():
    """Ni$_{3}$Sn$_{4}$ — math subscripts preserved."""
    result = escape_latex_smart("Ni$_{3}$Sn$_{4}$")
    assert "$_{3}$" in result
    assert "$_{4}$" in result


def test_smart_h_infinity():
    result = escape_latex_smart("$\\mathcal H_\\infty$ control")
    assert "$\\mathcal H_\\infty$" in result


def test_smart_combined_html_and_math():
    """HTML subscript and LaTeX math can coexist in the same title."""
    result = escape_latex_smart("$H_\\infty$ for CO<sub>2</sub>")
    assert "$H_\\infty$" in result
    assert r"\textsubscript{2}" in result


# ── clean_for_plaintext ──────────────────────────────────────────────────


def test_plaintext_plain():
    assert clean_for_plaintext("plain text") == "plain text"


def test_plaintext_empty():
    assert clean_for_plaintext("") == ""


def test_plaintext_none():
    assert clean_for_plaintext(None) is None


def test_plaintext_strips_italic():
    assert clean_for_plaintext("<i>in vitro</i>") == "in vitro"


def test_plaintext_sub_to_unicode():
    assert clean_for_plaintext("CO<sub>2</sub>") == "CO₂"


def test_plaintext_sup_to_unicode():
    assert clean_for_plaintext("x<sup>2</sup>") == "x²"


def test_plaintext_inf_to_unicode():
    assert clean_for_plaintext("CO<inf>2</inf>") == "CO₂"


def test_plaintext_strips_math_delimiters():
    result = clean_for_plaintext("$\\alpha$ value")
    assert "$" not in result
    assert "\\alpha" in result


def test_plaintext_strips_display_math():
    result = clean_for_plaintext("$$\\tau$$-lepton")
    assert "$" not in result


def test_plaintext_chemical_formula():
    result = clean_for_plaintext("CO<sub>2</sub> + H<sub>2</sub>O")
    assert result == "CO₂ + H₂O"
