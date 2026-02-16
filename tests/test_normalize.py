"""Tests for academia_orcid.normalize module."""

from academia_orcid.normalize import (
    strip_html_tags,
    html_to_latex,
    escape_latex_smart,
    clean_for_plaintext,
    _split_math_regions,
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


# ── html_to_latex ────────────────────────────────────────────────────────


def test_html_to_latex_italic():
    assert html_to_latex("<i>in vitro</i>") == r"\textit{in vitro}"


def test_html_to_latex_em():
    assert html_to_latex("<em>E. coli</em>") == r"\textit{E. coli}"


def test_html_to_latex_subscript():
    assert html_to_latex("CO<sub>2</sub>") == r"CO\textsubscript{2}"


def test_html_to_latex_inf():
    assert html_to_latex("CO<inf>2</inf>") == r"CO\textsubscript{2}"


def test_html_to_latex_superscript():
    assert html_to_latex("x<sup>2</sup>") == r"x\textsuperscript{2}"


def test_html_to_latex_scp():
    assert html_to_latex("<scp>PAAm</scp>") == r"\textsc{PAAm}"


def test_html_to_latex_bold():
    assert html_to_latex("<b>important</b>") == r"\textbf{important}"


def test_html_to_latex_strong():
    assert html_to_latex("<strong>key</strong>") == r"\textbf{key}"


def test_html_to_latex_remaining_stripped():
    result = html_to_latex('<mml:math>content</mml:math>')
    assert '<' not in result
    assert 'content' in result


def test_html_to_latex_no_tags():
    assert html_to_latex("plain text") == "plain text"


def test_html_to_latex_chemical_formula():
    text = "Mg<sub>2</sub>Si<sub>x</sub>Sn<sub>1-x</sub>"
    result = html_to_latex(text)
    assert r"\textsubscript{2}" in result
    assert r"\textsubscript{x}" in result
    assert r"\textsubscript{1-x}" in result


def test_html_to_latex_empty():
    assert html_to_latex("") == ""


def test_html_to_latex_none():
    assert html_to_latex(None) is None


# ── _split_math_regions ──────────────────────────────────────────────────


def test_split_no_math():
    result = _split_math_regions("plain text")
    assert result == [(False, "plain text")]


def test_split_inline_math():
    result = _split_math_regions("text $x^2$ more")
    assert len(result) == 3
    assert result[0] == (False, "text ")
    assert result[1] == (True, "$x^2$")
    assert result[2] == (False, " more")


def test_split_multiple_math():
    result = _split_math_regions("Ni$_{3}$Sn$_{4}$")
    math_parts = [s for is_math, s in result if is_math]
    assert len(math_parts) == 2
    assert "$_{3}$" in math_parts
    assert "$_{4}$" in math_parts


def test_split_math_at_start():
    result = _split_math_regions("$\\alpha$ decay")
    assert result[0] == (True, "$\\alpha$")
    assert result[1] == (False, " decay")


def test_split_math_at_end():
    result = _split_math_regions("value of $k$")
    assert result[-1] == (True, "$k$")


def test_split_unmatched_dollar():
    """Lone $ sign should stay in non-math text."""
    result = _split_math_regions("price is $50")
    assert all(not is_math for is_math, _ in result)


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
