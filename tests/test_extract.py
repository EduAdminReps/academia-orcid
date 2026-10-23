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
    filter_publications_by_period,
)
from academia_orcid.periods import ALL, period_from_flag


# ── filter_publications_by_period ──────────────────────────────────────────
# Parsing and the meaning of the flags are tested in coe-data-core
# (tests/test_periods.py); a publication's year is a calendar year.


def test_filter_by_calendar_range():
    pubs = [
        {"title": "Old", "year": "2018"},
        {"title": "In range", "year": "2022"},
        {"title": "Recent", "year": "2024"},
    ]
    result = filter_publications_by_period(pubs, period_from_flag("cal_year", "2020-2025"))
    assert [p["title"] for p in result] == ["In range", "Recent"]


def test_filter_all_years_keeps_everything():
    pubs = [{"title": "A", "year": "2020"}, {"title": "B", "year": "2024"}]
    assert filter_publications_by_period(pubs, ALL) == pubs


def test_filter_fiscal_year_spans_two_calendar_years():
    # FY2024 = Fall 2023 + Spring 2024
    pubs = [{"title": y, "year": y} for y in ("2022", "2023", "2024", "2025")]
    result = filter_publications_by_period(pubs, period_from_flag("year", "2024"))
    assert [p["title"] for p in result] == ["2023", "2024"]


def test_filter_academic_year_spans_two_calendar_years():
    pubs = [{"title": y, "year": y} for y in ("2022", "2023", "2024", "2025")]
    result = filter_publications_by_period(pubs, period_from_flag("acad_year", "2024"))
    assert [p["title"] for p in result] == ["2023", "2024"]


def test_filter_open_ended():
    pubs = [{"title": y, "year": y} for y in ("2019", "2020", "2026")]
    result = filter_publications_by_period(pubs, period_from_flag("cal_year", "2020+"))
    assert [p["title"] for p in result] == ["2020", "2026"]


def test_filter_semester():
    pubs = [{"title": y, "year": y} for y in ("2023", "2024")]
    result = filter_publications_by_period(pubs, period_from_flag("semester", "202431"))
    assert [p["title"] for p in result] == ["2024"]


def test_filter_missing_or_unparseable_year_kept():
    pubs = [
        {"title": "No year", "year": ""},
        {"title": "Odd year", "year": "circa 2020"},
        {"title": "Has year", "year": "2022"},
        {"title": "Out", "year": "2010"},
    ]
    result = filter_publications_by_period(pubs, period_from_flag("cal_year", "2020-2025"))
    assert [p["title"] for p in result] == ["No year", "Odd year", "Has year"]


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
