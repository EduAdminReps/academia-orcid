"""Text normalization for ORCID data fields.

The functions live in the vendored coe_core.latex (latex_text.py; refreshed from
coe-data-core with `just vendor-set`), one copy shared with tamu-scholars:

- strip_html_tags()     -- format-agnostic: remove all HTML, keep text
- escape_latex_smart()  -- LaTeX output: HTML tags and $...$ math to LaTeX, the
                           tags' content escaped and their nesting kept (audit
                           ORC-05), characters pdflatex cannot set dropped
- clean_for_plaintext() -- JSON/DOCX output: strip HTML, Unicode sub/superscripts
"""

from academia_orcid.latex_text import clean_for_plaintext, markup_to_latex, strip_html_tags

escape_latex_smart = markup_to_latex

__all__ = ["clean_for_plaintext", "escape_latex_smart", "strip_html_tags"]
