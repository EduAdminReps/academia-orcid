"""Tests for academia_orcid.extract module."""

import pytest

from academia_orcid.extract import (
    extract_biography,
    extract_distinctions,
    extract_educations,
    extract_employments,
    extract_external_identifiers,
    extract_fundings,
    extract_memberships,
    extract_publications,
    extract_services,
    normalize_doi,
    split_name,
)
from tests.conftest import _make_work

# The report period is the composer's (tamu-coe-faculty-profiles,
# formatters/publications.py): this repo returns every publication.


# ── extract_publications ───────────────────────────────────────────────────


def test_extract_publications_categorizes(sample_record):
    journals, conferences, other = extract_publications(sample_record)
    assert len(journals) == 1
    assert len(conferences) == 1
    assert len(other) == 1
    assert journals[0]["title"] == "A Journal Paper"
    assert conferences[0]["title"] == "A Conference Paper"
    assert other[0]["title"] == "A Book Chapter"


def test_extract_publications_empty(empty_record):
    journals, conferences, other = extract_publications(empty_record)
    assert journals == []
    assert conferences == []
    assert other == []


def test_extract_publications_sorted(sample_record):
    journals, conferences, other = extract_publications(sample_record)
    # Journal has 2024, conference 2023, book 2022 — each list has 1 item
    # but verify the year is present
    assert journals[0]["year"] == "2024"
    assert conferences[0]["year"] == "2023"
    assert other[0]["year"] == "2022"


# ── extract data fields ───────────────────────────────────────────────────


def test_extract_biography(sample_record):
    bio = extract_biography(sample_record)
    # Should unescape HTML entities
    assert bio == "Researcher at Texas A&M University."


def test_extract_employments(sample_record):
    emps = extract_employments(sample_record)
    assert len(emps) == 1
    assert emps[0]["organization"] == "Texas A&M University"
    assert emps[0]["role"] == "Professor"
    assert emps[0]["department"] == "Electrical Engineering"
    assert emps[0]["start_year"] == "2015"


def test_extract_fundings(sample_record):
    funds = extract_fundings(sample_record)
    assert len(funds) == 1
    assert funds[0]["title"] == "Research Grant"
    assert funds[0]["organization"] == "NSF"
    assert funds[0]["type"] == "grant"
    assert funds[0]["start_year"] == "2022"
    assert funds[0]["end_year"] == "2025"


def test_extract_empty_record(empty_record):
    assert extract_biography(empty_record) is None
    assert extract_external_identifiers(empty_record) == []
    assert extract_employments(empty_record) == []
    assert extract_educations(empty_record) == []
    assert extract_distinctions(empty_record) == []
    assert extract_memberships(empty_record) == []
    assert extract_services(empty_record) == []
    assert extract_fundings(empty_record) == []


# ── Real ORCID shapes (audit ORC-01, ORC-02, ORC-06, ORC-10, ORC-16) ───────
# The fixture builder above only makes tidy works; these use the shapes the
# cache actually holds.


def _record(*groups):
    return {"activities-summary": {"works": {"group": list(groups)}}}


def _work(**fields):
    """A work-summary dict with null where ORCID sends null, wrapped as a group."""
    work = {
        "type": "journal-article",
        "title": {"title": {"value": "A title long enough to compare"}},
        "publication-date": {"year": {"value": "2024"}},
        "external-ids": None,
        "contributors": None,
        "journal-title": None,
        "url": None,
        "citation": None,
    }
    work.update(fields)
    return {"work-summary": [work]}


def test_null_publication_date_keeps_the_work():
    """614 cached works carry "publication-date": null; they used to vanish (ORC-02)."""
    journals, _, _ = extract_publications(_record(_work(**{"publication-date": None})))
    assert len(journals) == 1 and journals[0]["year"] == "" and journals[0]["month"] == ""


def test_null_title_and_contributors_keep_the_work():
    journals, _, _ = extract_publications(_record(_work(title=None, contributors=None)))
    assert journals[0]["title"] == "Untitled" and journals[0]["author_names"] == []


@pytest.mark.parametrize(
    ("raw", "family", "given"),
    [
        ("Jane A. Doe", "Doe", "Jane A."),
        ("Doe, Jane A.", "Doe", "Jane A."),  # 56% of credit-names are family-first
        ("Doe, J.", "Doe", "J."),
        ("Doe J", "Doe", "J"),
        ("Smith JA", "Smith", "JA"),
        ("Smith John A", "Smith", "John A"),  # a trailing initial: family first
        ("Jean-Pierre Martin", "Martin", "Jean-Pierre"),
        ("van der Berg, Anna", "van der Berg", "Anna"),
        ("Doe, Jane, Jr.", "Doe", "Jane  Jr."),
        ("Madonna", "Madonna", ""),
    ],
)
def test_author_names_in_either_order(raw, family, given):
    assert split_name(raw) == (family, given)


def test_family_first_authors_in_a_work():
    contributors = {
        "contributor": [{"credit-name": {"value": n}} for n in ["Doe, Jane A.", "Bo Li"]]
    }
    journals, _, _ = extract_publications(_record(_work(contributors=contributors)))
    assert journals[0]["author_names"] == [
        {"family": "Doe", "given": "Jane A."},
        {"family": "Li", "given": "Bo"},
    ]
    assert "authors" not in journals[0]  # the composer renders author_names


def test_author_names_are_structured_and_complete():
    """author_names: every credit name as {family, given}; the composer cuts to "et al."."""
    names = ["Doe, Jane A.", "Bo Li", "Smith JA", "Madonna"] + [f"Ann Extra{i}" for i in range(9)]
    contributors = {"contributor": [{"credit-name": {"value": n}} for n in names]}
    journals, _, _ = extract_publications(_record(_work(contributors=contributors)))
    parsed = journals[0]["author_names"]
    assert parsed[:4] == [
        {"family": "Doe", "given": "Jane A."},
        {"family": "Li", "given": "Bo"},
        {"family": "Smith", "given": "JA"},
        {"family": "Madonna", "given": ""},
    ]
    assert len(parsed) == len(names)
    assert journals[0]["raw_authors"] == names


@pytest.mark.parametrize(
    ("raw", "doi"),
    [
        ("https://doi.org/10.1000/ABC", "10.1000/ABC"),
        ("http://dx.doi.org/10.5555/q", "10.5555/q"),
        ("doi:10.1234/x", "10.1234/x"),
        (" 10.1234/x.y ", "10.1234/x.y"),
        ("not a doi", ""),
    ],
)
def test_normalize_doi(raw, doi):
    assert normalize_doi(raw) == doi


def _ids(*pairs):
    return {
        "external-id": [
            {"external-id-type": "doi", "external-id-value": v, "external-id-relationship": r}
            for v, r in pairs
        ]
    }


def test_doi_is_the_works_own_never_its_books():
    """A chapter lists its book's DOI as part-of; the entry shows the chapter's own (ORC-06)."""
    chapter = _work(
        **{"external-ids": _ids(("10.1000/book", "part-of"), ("10.1000/book.ch3", "self"))}
    )
    only_book = _work(
        **{"external-ids": _ids(("10.1000/other", "part-of"))},
        title={"title": {"value": "Another chapter title of some length"}},
    )
    journals, _, _ = extract_publications(_record(chapter, only_book))
    assert sorted(p["doi"] for p in journals) == ["", "10.1000/book.ch3"]


def test_url_form_doi_is_stored_bare():
    work = _work(**{"external-ids": _ids(("https://doi.org/10.1000/abc", "self"))})
    journals, _, _ = extract_publications(_record(work))
    assert (
        journals[0]["doi"] == "10.1000/abc" and journals[0]["external_ids"]["doi"] == "10.1000/abc"
    )


def test_duplicate_works_are_collapsed():
    """Same DOI, or the same type, title and year without a DOI: one entry (ORC-10)."""
    groups = [
        _make_work("journal-article", "Graph learning for power systems", "2024", doi="10.1000/a"),
        _make_work("journal-article", "Graph learning for power systems", "2024"),  # copy, no DOI
        _make_work(
            "conference-paper", "Graph learning, conference version", "2024", doi="10.1000/A"
        ),
        _make_work("journal-article", "Graph learning for power systems", "2023"),  # other year
        _make_work("journal-article", "Editorial", "2024"),
        _make_work("journal-article", "Editorial", "2024"),  # too short to compare: both kept
    ]
    journals, conferences, others = extract_publications(_record(*groups))
    assert [(p["title"], p["year"], p["doi"]) for p in journals] == [
        ("Graph learning for power systems", "2024", "10.1000/a"),
        ("Editorial", "2024", ""),
        ("Editorial", "2024", ""),
        ("Graph learning for power systems", "2023", ""),
    ]
    assert conferences == []  # same DOI as the journal article: kept as the article


def test_title_keeps_markup_with_whitespace_collapsed():
    """The composer renders the markup; line breaks and indentation are not content."""
    raw = "Abundance in\n            <i>In Vitro</i>\n            Cocultures &amp; more"
    journals, _, _ = extract_publications(_record(_work(title={"title": {"value": raw}})))
    assert journals[0]["title"] == "Abundance in <i>In Vitro</i> Cocultures & more"
