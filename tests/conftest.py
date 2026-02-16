"""Shared pytest fixtures for academia_orcid tests."""

import json

import pytest


def _make_work(pub_type, title, year, venue="", doi="", authors=None):
    """Helper to build a minimal ORCID work-group entry."""
    contributors = []
    for name in (authors or []):
        contributors.append({"credit-name": {"value": name}})

    work_summary = {
        "type": pub_type,
        "title": {"title": {"value": title}},
        "publication-date": {"year": {"value": year}},
        "journal-title": {"value": venue} if venue else None,
        "contributors": {"contributor": contributors} if contributors else None,
        "external-ids": {
            "external-id": [
                {"external-id-type": "doi", "external-id-value": doi}
            ] if doi else []
        },
    }
    return {"work-summary": [work_summary]}


def _make_affiliation(summary_key, org_name, role="", department="",
                      start_year="", end_year="", city="", country=""):
    """Helper to build a minimal affiliation-group entry."""
    return {
        "summaries": [{
            summary_key: {
                "organization": {
                    "name": org_name,
                    "address": {"city": city, "region": "", "country": country},
                },
                "role-title": role,
                "department-name": department,
                "start-date": {"year": {"value": start_year}} if start_year else None,
                "end-date": {"year": {"value": end_year}} if end_year else None,
            }
        }]
    }


@pytest.fixture
def sample_record():
    """A minimal but complete ORCID record with data in every section."""
    return {
        "person": {
            "biography": {
                "content": "Researcher at Texas A&amp;M University.",
                "visibility": "public",
            },
            "external-identifiers": {
                "external-identifier": [
                    {
                        "external-id-type": "Scopus Author ID",
                        "external-id-value": "123456789",
                        "external-id-url": {"value": "https://scopus.com/123456789"},
                    }
                ]
            },
        },
        "activities-summary": {
            "works": {
                "group": [
                    _make_work(
                        "journal-article",
                        "A Journal Paper",
                        "2024",
                        venue="IEEE Trans. Signal Processing",
                        doi="10.1109/TSP.2024.001",
                        authors=["Alice Smith", "Bob Jones"],
                    ),
                    _make_work(
                        "conference-paper",
                        "A Conference Paper",
                        "2023",
                        venue="Proc. IEEE ICASSP",
                        authors=["Alice Smith"],
                    ),
                    _make_work(
                        "book",
                        "A Book Chapter",
                        "2022",
                        venue="Springer",
                    ),
                ],
            },
            "employments": {
                "affiliation-group": [
                    _make_affiliation(
                        "employment-summary",
                        "Texas A&M University",
                        role="Professor",
                        department="Electrical Engineering",
                        start_year="2015",
                        city="College Station",
                        country="US",
                    ),
                ],
            },
            "educations": {
                "affiliation-group": [
                    _make_affiliation(
                        "education-summary",
                        "MIT",
                        role="Ph.D.",
                        department="EECS",
                        start_year="2008",
                        end_year="2013",
                        city="Cambridge",
                        country="US",
                    ),
                ],
            },
            "distinctions": {
                "affiliation-group": [
                    _make_affiliation(
                        "distinction-summary",
                        "IEEE",
                        role="Fellow",
                        start_year="2020",
                    ),
                ],
            },
            "memberships": {
                "affiliation-group": [
                    _make_affiliation(
                        "membership-summary",
                        "IEEE",
                        role="Senior Member",
                        start_year="2018",
                    ),
                ],
            },
            "services": {
                "affiliation-group": [
                    _make_affiliation(
                        "service-summary",
                        "IEEE Trans. Info Theory",
                        role="Associate Editor",
                        start_year="2021",
                    ),
                ],
            },
            "fundings": {
                "group": [
                    {
                        "funding-summary": [{
                            "title": {"title": {"value": "Research Grant"}},
                            "organization": {"name": "NSF"},
                            "type": "grant",
                            "start-date": {"year": {"value": "2022"}},
                            "end-date": {"year": {"value": "2025"}},
                        }],
                    },
                ],
            },
        },
    }


@pytest.fixture
def empty_record():
    """An ORCID record with no data in any section."""
    return {
        "person": {},
        "activities-summary": {},
    }


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Temp directory with a cached ORCID JSON record."""
    # Create cached JSON
    json_dir = tmp_path / "ORCID_JSON"
    json_dir.mkdir()
    record = {"person": {}, "activities-summary": {"works": {"group": []}}}
    json_file = json_dir / "0000-0001-2345-6789.json"
    json_file.write_text(json.dumps(record))

    return tmp_path
