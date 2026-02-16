"""Tests for academia_orcid.extract module."""

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
    filter_publications_by_year,
    parse_year_filter,
)


# ── parse_year_filter ──────────────────────────────────────────────────────


def test_parse_year_filter_range():
    assert parse_year_filter("2020-2025") == (2020, 2025)


def test_parse_year_filter_single():
    assert parse_year_filter("2024") == (2024, 2024)


def test_parse_year_filter_all():
    assert parse_year_filter("all") is None


def test_parse_year_filter_none():
    assert parse_year_filter(None) is None


def test_parse_year_filter_invalid():
    assert parse_year_filter("abc") is None


# ── filter_publications_by_year ────────────────────────────────────────────


def test_filter_by_year_range():
    pubs = [
        {"title": "Old", "year": "2018"},
        {"title": "In range", "year": "2022"},
        {"title": "Recent", "year": "2024"},
    ]
    result = filter_publications_by_year(pubs, (2020, 2025))
    assert len(result) == 2
    assert result[0]["title"] == "In range"
    assert result[1]["title"] == "Recent"


def test_filter_by_year_none():
    pubs = [{"title": "A", "year": "2020"}, {"title": "B", "year": "2024"}]
    result = filter_publications_by_year(pubs, None)
    assert len(result) == 2


def test_filter_by_year_missing_year():
    pubs = [
        {"title": "No year", "year": ""},
        {"title": "Has year", "year": "2022"},
    ]
    result = filter_publications_by_year(pubs, (2020, 2025))
    # Publications with no year are always included
    assert len(result) == 2


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
