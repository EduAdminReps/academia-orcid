"""Tests for BibTeX export functionality."""

import pytest

from academia_orcid.bibtex_export import (
    ORCID_TO_BIBTEX_TYPE,
    _escape_bibtex,
    _extract_cite_key_from_bibtex,
    _format_authors_bibtex,
    _generate_cite_key,
    _get_first_author_last_name,
    _normalize_embedded_bibtex,
    _pub_to_bibtex_entry,
    export_bibtex,
)
from academia_orcid.extract import extract_publications


# ── Cite key generation ──────────────────────────────────────────────────


class TestCiteKeyGeneration:
    def test_basic(self):
        seen = {}
        key = _generate_cite_key("Smith", "2024", seen)
        assert key == "Smith2024"

    def test_duplicate_keys(self):
        seen = {}
        k1 = _generate_cite_key("Smith", "2024", seen)
        k2 = _generate_cite_key("Smith", "2024", seen)
        k3 = _generate_cite_key("Smith", "2024", seen)
        assert k1 == "Smith2024"
        assert k2 == "Smith2024a"
        assert k3 == "Smith2024b"

    def test_unicode_folding(self):
        seen = {}
        key = _generate_cite_key("Müller", "2023", seen)
        assert key == "Muller2023"

    def test_missing_year(self):
        seen = {}
        key = _generate_cite_key("Jones", "", seen)
        assert key == "JonesNoYear"

    def test_empty_name(self):
        seen = {}
        key = _generate_cite_key("", "2024", seen)
        assert key == "Unknown2024"

    def test_special_characters_stripped(self):
        seen = {}
        key = _generate_cite_key("O'Brien-Smith", "2024", seen)
        assert key == "OBrienSmith2024"

    def test_different_years_no_suffix(self):
        seen = {}
        k1 = _generate_cite_key("Smith", "2023", seen)
        k2 = _generate_cite_key("Smith", "2024", seen)
        assert k1 == "Smith2023"
        assert k2 == "Smith2024"


# ── Author formatting ────────────────────────────────────────────────────


class TestAuthorFormatting:
    def test_single_author(self):
        result = _format_authors_bibtex(["Alice Smith"])
        assert result == "Smith, Alice"

    def test_multiple_authors(self):
        result = _format_authors_bibtex(["Alice Smith", "Bob Jones"])
        assert result == "Smith, Alice and Jones, Bob"

    def test_mononym(self):
        result = _format_authors_bibtex(["Madonna"])
        assert result == "Madonna"

    def test_three_part_name(self):
        result = _format_authors_bibtex(["Alice Marie Smith"])
        assert result == "Smith, Alice Marie"

    def test_html_entities(self):
        result = _format_authors_bibtex(["Jos&eacute; Garc&iacute;a"])
        assert "José" in result
        assert "García" in result

    def test_empty_list(self):
        assert _format_authors_bibtex([]) == ""


# ── BibTeX escaping ──────────────────────────────────────────────────────


class TestEscapeBibtex:
    def test_html_stripped(self):
        result = _escape_bibtex("<i>Italic</i> text")
        assert result == "Italic text"
        assert "<i>" not in result

    def test_html_entities_unescaped(self):
        result = _escape_bibtex("A &amp; B")
        assert result == "A & B"

    def test_latex_math_preserved(self):
        result = _escape_bibtex("Title with $\\alpha$ symbol")
        assert "$\\alpha$" in result

    def test_empty(self):
        assert _escape_bibtex("") == ""

    def test_none_like(self):
        assert _escape_bibtex("") == ""


# ── Entry type mapping ───────────────────────────────────────────────────


class TestEntryTypeMapping:
    def test_journal_article(self):
        assert ORCID_TO_BIBTEX_TYPE["journal-article"] == "article"

    def test_conference_paper(self):
        assert ORCID_TO_BIBTEX_TYPE["conference-paper"] == "inproceedings"

    def test_book(self):
        assert ORCID_TO_BIBTEX_TYPE["book"] == "book"

    def test_book_chapter(self):
        assert ORCID_TO_BIBTEX_TYPE["book-chapter"] == "incollection"

    def test_dissertation(self):
        assert ORCID_TO_BIBTEX_TYPE["dissertation"] == "phdthesis"

    def test_report(self):
        assert ORCID_TO_BIBTEX_TYPE["report"] == "techreport"

    def test_preprint(self):
        assert ORCID_TO_BIBTEX_TYPE["preprint"] == "unpublished"


# ── First author extraction ──────────────────────────────────────────────


class TestFirstAuthorLastName:
    def test_from_raw_authors(self):
        pub = {"raw_authors": ["Alice Smith", "Bob Jones"]}
        assert _get_first_author_last_name(pub) == "Smith"

    def test_from_formatted_authors(self):
        pub = {"authors": "Smith, A., Jones, B."}
        assert _get_first_author_last_name(pub) == "Smith"

    def test_no_authors(self):
        pub = {}
        assert _get_first_author_last_name(pub) == "Unknown"

    def test_empty_raw_authors(self):
        pub = {"raw_authors": []}
        assert _get_first_author_last_name(pub) == "Unknown"


# ── Single entry generation ──────────────────────────────────────────────


class TestPubToBibtexEntry:
    def test_journal_article(self):
        pub = {
            "raw_authors": ["Alice Smith", "Bob Jones"],
            "title": "A Great Paper",
            "venue": "Nature",
            "year": "2024",
            "month": "03",
            "doi": "10.1038/s41586-024-001",
            "url": "",
            "pub_type": "journal-article",
            "external_ids": {},
        }
        result = _pub_to_bibtex_entry(pub, "Smith2024")
        assert result.startswith("@article{Smith2024,")
        assert "author = {Smith, Alice and Jones, Bob}" in result
        assert "title = {{A Great Paper}}" in result
        assert "journal = {Nature}" in result
        assert "year = {2024}" in result
        assert "month = mar" in result
        assert "doi = {10.1038/s41586-024-001}" in result

    def test_conference_paper(self):
        pub = {
            "raw_authors": ["Alice Smith"],
            "title": "Conference Talk",
            "venue": "Proc. IEEE ICASSP",
            "year": "2023",
            "month": "",
            "doi": "",
            "url": "",
            "pub_type": "conference-paper",
            "external_ids": {},
        }
        result = _pub_to_bibtex_entry(pub, "Smith2023")
        assert result.startswith("@inproceedings{Smith2023,")
        assert "booktitle = {Proc. IEEE ICASSP}" in result

    def test_minimal_entry(self):
        pub = {
            "raw_authors": [],
            "title": "Untitled",
            "venue": "",
            "year": "2024",
            "month": "",
            "doi": "",
            "url": "",
            "pub_type": "other",
            "external_ids": {},
        }
        result = _pub_to_bibtex_entry(pub, "Unknown2024")
        assert result.startswith("@misc{Unknown2024,")
        assert "title = {{Untitled}}" in result
        assert "year = {2024}" in result
        assert "author" not in result

    def test_with_url(self):
        pub = {
            "raw_authors": ["Alice Smith"],
            "title": "Online Resource",
            "venue": "",
            "year": "2024",
            "month": "",
            "doi": "",
            "url": "https://example.com/paper",
            "pub_type": "online-resource",
            "external_ids": {},
        }
        result = _pub_to_bibtex_entry(pub, "Smith2024")
        assert "url = {https://example.com/paper}" in result

    def test_with_isbn(self):
        pub = {
            "raw_authors": ["Alice Smith"],
            "title": "A Book",
            "venue": "Publisher",
            "year": "2024",
            "month": "",
            "doi": "",
            "url": "",
            "pub_type": "book",
            "external_ids": {"isbn": "978-0-123456-78-9"},
        }
        result = _pub_to_bibtex_entry(pub, "Smith2024")
        assert "isbn = {978-0-123456-78-9}" in result

    def test_enriched_fields(self):
        """Test that volume/pages/number from enrichment are included."""
        pub = {
            "raw_authors": ["Alice Smith"],
            "title": "A Paper",
            "venue": "Nature",
            "year": "2024",
            "month": "",
            "doi": "10.1038/001",
            "url": "",
            "pub_type": "journal-article",
            "external_ids": {},
            "volume": "42",
            "pages": "100-110",
            "number": "3",
        }
        result = _pub_to_bibtex_entry(pub, "Smith2024")
        assert "volume = {42}" in result
        assert "pages = {100-110}" in result
        assert "number = {3}" in result


# ── Embedded BibTeX handling ─────────────────────────────────────────────


class TestEmbeddedBibtex:
    def test_extract_cite_key(self):
        bib = '@article{Smith_2024, title={Paper}}'
        assert _extract_cite_key_from_bibtex(bib) == "Smith_2024"

    def test_extract_cite_key_inproceedings(self):
        bib = '@inproceedings{Jones2023a, author={Jones}}'
        assert _extract_cite_key_from_bibtex(bib) == "Jones2023a"

    def test_extract_cite_key_invalid(self):
        assert _extract_cite_key_from_bibtex("not bibtex") is None

    def test_normalize_tabs(self):
        bib = "@article{key,\ttitle={Paper},\tyear={2024}}"
        result = _normalize_embedded_bibtex(bib)
        assert "\t" not in result
        assert "\n" in result

    def test_normalize_already_formatted(self):
        bib = "@article{key,\n  title={Paper},\n  year={2024}\n}"
        result = _normalize_embedded_bibtex(bib)
        assert result == bib


# ── Full export ──────────────────────────────────────────────────────────


class TestExportBibtex:
    def test_empty_returns_empty(self):
        result = export_bibtex("0000-0001-2345-6789", [], [], [])
        assert result == ""

    def test_header_comment(self):
        pubs = [{
            "raw_authors": ["Alice Smith"],
            "authors": "Smith, A.",
            "title": "Paper",
            "venue": "Journal",
            "year": "2024",
            "month": "",
            "doi": "",
            "url": "",
            "pub_type": "journal-article",
            "external_ids": {},
            "citation": None,
        }]
        result = export_bibtex("0000-0001-2345-6789", pubs, [], [])
        assert "% BibTeX export from ORCID record: 0000-0001-2345-6789" in result
        assert "% Source: https://orcid.org/0000-0001-2345-6789" in result
        assert "% Entries: 1 total" in result

    def test_generated_entry(self):
        pubs = [{
            "raw_authors": ["Alice Smith"],
            "authors": "Smith, A.",
            "title": "My Paper",
            "venue": "Nature",
            "year": "2024",
            "month": "",
            "doi": "10.1038/001",
            "url": "",
            "pub_type": "journal-article",
            "external_ids": {},
            "citation": None,
        }]
        result = export_bibtex("0000-0001-2345-6789", pubs, [], [])
        assert "@article{Smith2024," in result
        assert "title = {{My Paper}}" in result
        assert "(0 from ORCID, 1 generated)" in result

    def test_embedded_bibtex_preferred(self):
        pubs = [{
            "raw_authors": ["Alice Smith"],
            "authors": "Smith, A.",
            "title": "Paper",
            "venue": "Nature",
            "year": "2024",
            "month": "",
            "doi": "10.1038/001",
            "url": "",
            "pub_type": "journal-article",
            "external_ids": {},
            "citation": {
                "citation-type": "bibtex",
                "citation-value": "@article{Smith_2024,\n  title={Embedded},\n  year={2024}\n}",
            },
        }]
        result = export_bibtex("0000-0001-2345-6789", pubs, [], [])
        assert "title={Embedded}" in result
        assert "(1 from ORCID, 0 generated)" in result

    def test_non_bibtex_citation_ignored(self):
        pubs = [{
            "raw_authors": ["Alice Smith"],
            "authors": "Smith, A.",
            "title": "Paper",
            "venue": "Nature",
            "year": "2024",
            "month": "",
            "doi": "",
            "url": "",
            "pub_type": "journal-article",
            "external_ids": {},
            "citation": {
                "citation-type": "ris",
                "citation-value": "TY  - JOUR\nTI  - Paper\n",
            },
        }]
        result = export_bibtex("0000-0001-2345-6789", pubs, [], [])
        # Should fall back to generated since it's not bibtex type
        assert "(0 from ORCID, 1 generated)" in result

    def test_mixed_embedded_and_generated(self):
        embedded_pub = {
            "raw_authors": ["Alice Smith"],
            "authors": "Smith, A.",
            "title": "Embedded",
            "venue": "Nature",
            "year": "2024",
            "month": "",
            "doi": "",
            "url": "",
            "pub_type": "journal-article",
            "external_ids": {},
            "citation": {
                "citation-type": "bibtex",
                "citation-value": "@article{Smith_2024, title={Embedded}}",
            },
        }
        generated_pub = {
            "raw_authors": ["Bob Jones"],
            "authors": "Jones, B.",
            "title": "Generated",
            "venue": "Science",
            "year": "2023",
            "month": "",
            "doi": "",
            "url": "",
            "pub_type": "journal-article",
            "external_ids": {},
            "citation": None,
        }
        result = export_bibtex("0000-0001-2345-6789", [embedded_pub, generated_pub], [], [])
        assert "(1 from ORCID, 1 generated)" in result
        assert "title={Embedded}" in result
        assert "@article{Jones2023," in result

    def test_duplicate_embedded_keys(self):
        pub1 = {
            "raw_authors": ["Alice Smith"],
            "authors": "Smith, A.",
            "title": "Paper 1",
            "venue": "",
            "year": "2024",
            "month": "",
            "doi": "",
            "url": "",
            "pub_type": "journal-article",
            "external_ids": {},
            "citation": {
                "citation-type": "bibtex",
                "citation-value": "@article{Smith2024, title={Paper 1}}",
            },
        }
        pub2 = {
            "raw_authors": ["Alice Smith"],
            "authors": "Smith, A.",
            "title": "Paper 2",
            "venue": "",
            "year": "2024",
            "month": "",
            "doi": "",
            "url": "",
            "pub_type": "journal-article",
            "external_ids": {},
            "citation": {
                "citation-type": "bibtex",
                "citation-value": "@article{Smith2024, title={Paper 2}}",
            },
        }
        result = export_bibtex("0000-0001-2345-6789", [pub1, pub2], [], [])
        # First keeps original key, second gets deduplicated
        assert "Smith2024," in result
        # Should have two entries
        assert result.count("@article{") == 2

    def test_all_categories(self):
        journal = {
            "raw_authors": ["A Smith"],
            "authors": "Smith, A.",
            "title": "J",
            "venue": "J1",
            "year": "2024",
            "month": "",
            "doi": "",
            "url": "",
            "pub_type": "journal-article",
            "external_ids": {},
            "citation": None,
        }
        conf = {
            "raw_authors": ["B Jones"],
            "authors": "Jones, B.",
            "title": "C",
            "venue": "C1",
            "year": "2023",
            "month": "",
            "doi": "",
            "url": "",
            "pub_type": "conference-paper",
            "external_ids": {},
            "citation": None,
        }
        other = {
            "raw_authors": ["C Lee"],
            "authors": "Lee, C.",
            "title": "O",
            "venue": "P1",
            "year": "2022",
            "month": "",
            "doi": "",
            "url": "",
            "pub_type": "book",
            "external_ids": {},
            "citation": None,
        }
        result = export_bibtex("0000-0001-2345-6789", [journal], [conf], [other])
        assert "% Entries: 3 total" in result
        assert "@article{" in result
        assert "@inproceedings{" in result
        assert "@book{" in result


# ── Integration with extract.py ──────────────────────────────────────────


class TestExtractIntegration:
    """Verify that extract_publications() produces new fields."""

    def test_raw_authors_present(self, sample_record):
        journals, _, _ = extract_publications(sample_record)
        assert len(journals) == 1
        assert "raw_authors" in journals[0]
        assert journals[0]["raw_authors"] == ["Alice Smith", "Bob Jones"]

    def test_pub_type_present(self, sample_record):
        journals, confs, other = extract_publications(sample_record)
        assert journals[0]["pub_type"] == "journal-article"
        assert confs[0]["pub_type"] == "conference-paper"
        assert other[0]["pub_type"] == "book"

    def test_doi_still_works(self, sample_record):
        journals, _, _ = extract_publications(sample_record)
        assert journals[0]["doi"] == "10.1109/TSP.2024.001"

    def test_external_ids_dict(self, sample_record):
        journals, _, _ = extract_publications(sample_record)
        ext = journals[0]["external_ids"]
        assert isinstance(ext, dict)
        assert ext.get("doi") == "10.1109/TSP.2024.001"

    def test_citation_field_present(self, sample_record):
        journals, _, _ = extract_publications(sample_record)
        assert "citation" in journals[0]

    def test_month_and_url_default_empty(self, sample_record):
        journals, _, _ = extract_publications(sample_record)
        assert journals[0]["month"] == ""
        assert journals[0]["url"] == ""

    def test_month_extracted(self):
        record = {
            "activities-summary": {
                "works": {
                    "group": [{
                        "work-summary": [{
                            "type": "journal-article",
                            "title": {"title": {"value": "Paper"}},
                            "publication-date": {
                                "year": {"value": "2024"},
                                "month": {"value": "06"},
                            },
                            "journal-title": None,
                            "contributors": {"contributor": [
                                {"credit-name": {"value": "Smith"}}
                            ]},
                            "external-ids": {"external-id": []},
                        }]
                    }]
                }
            }
        }
        journals, _, _ = extract_publications(record)
        assert journals[0]["month"] == "06"

    def test_url_extracted(self):
        record = {
            "activities-summary": {
                "works": {
                    "group": [{
                        "work-summary": [{
                            "type": "journal-article",
                            "title": {"title": {"value": "Paper"}},
                            "publication-date": {"year": {"value": "2024"}},
                            "journal-title": None,
                            "contributors": {"contributor": [
                                {"credit-name": {"value": "Smith"}}
                            ]},
                            "external-ids": {"external-id": []},
                            "url": {"value": "https://example.com/paper"},
                        }]
                    }]
                }
            }
        }
        journals, _, _ = extract_publications(record)
        assert journals[0]["url"] == "https://example.com/paper"

    def test_extra_external_ids(self):
        record = {
            "activities-summary": {
                "works": {
                    "group": [{
                        "work-summary": [{
                            "type": "book",
                            "title": {"title": {"value": "A Book"}},
                            "publication-date": {"year": {"value": "2024"}},
                            "journal-title": None,
                            "contributors": {"contributor": [
                                {"credit-name": {"value": "Smith"}}
                            ]},
                            "external-ids": {"external-id": [
                                {"external-id-type": "doi", "external-id-value": "10.1000/b1"},
                                {"external-id-type": "isbn", "external-id-value": "978-0-123456-78-9"},
                            ]},
                        }]
                    }]
                }
            }
        }
        _, _, other = extract_publications(record)
        assert other[0]["external_ids"]["doi"] == "10.1000/b1"
        assert other[0]["external_ids"]["isbn"] == "978-0-123456-78-9"

    def test_citation_data_passed_through(self):
        citation = {"citation-type": "bibtex", "citation-value": "@article{key,}"}
        record = {
            "activities-summary": {
                "works": {
                    "group": [{
                        "work-summary": [{
                            "type": "journal-article",
                            "title": {"title": {"value": "Paper"}},
                            "publication-date": {"year": {"value": "2024"}},
                            "journal-title": None,
                            "contributors": {"contributor": [
                                {"credit-name": {"value": "Smith"}}
                            ]},
                            "external-ids": {"external-id": []},
                            "citation": citation,
                        }]
                    }]
                }
            }
        }
        journals, _, _ = extract_publications(record)
        assert journals[0]["citation"] == citation
