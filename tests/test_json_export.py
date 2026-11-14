"""Tests for JSON export functionality."""

from datetime import datetime

from academia_orcid.json_export import export_data, export_publications

# ── export_publications ───────────────────────────────────────────────────


def test_export_publications_all_categories():
    """Test export with all publication categories present."""
    journals = [
        {
            "title": "Journal Paper 1",
            "year": "2024",
            "doi": "10.1000/j1",
            "raw_authors": ["A. Smith"],
            "venue": "Nature",
        },
        {
            "title": "Journal Paper 2",
            "year": "2023",
            "doi": "",
            "raw_authors": ["B. Jones"],
            "venue": "Science",
        },
    ]
    conferences = [
        {
            "title": "Conference Paper",
            "year": "2024",
            "doi": "10.1000/c1",
            "raw_authors": ["C. Lee"],
            "venue": "ICML",
        },
    ]
    other = [
        {
            "title": "Book Chapter",
            "year": "2022",
            "doi": "",
            "raw_authors": ["D. Wang"],
            "venue": "Springer",
        },
    ]

    result = export_publications("0000-0001-2345-6789", journals, conferences, other)

    assert result["_meta"]["section"] == "orcid-publications"
    assert result["_meta"]["orcid_id"] == "0000-0001-2345-6789"
    assert result["_meta"]["total_count"] == 4
    assert "generated_at" in result["_meta"]

    assert len(result["journal_articles"]) == 2
    assert len(result["conference_papers"]) == 1
    assert len(result["other_publications"]) == 1

    # Verify structure
    assert result["journal_articles"][0]["title"] == "Journal Paper 1"
    assert result["journal_articles"][0]["year"] == "2024"


def test_export_publications_empty_lists():
    """Test export with all empty lists returns empty dict."""
    result = export_publications("0000-0001-2345-6789", [], [], [])

    assert result == {}


def test_export_publications_partial_data():
    """Test export with only some categories populated."""
    journals = [
        {"title": "Paper", "year": "2024", "doi": "", "raw_authors": ["Smith"], "venue": "Journal"}
    ]
    conferences = []
    other = []

    result = export_publications("0000-0001-2345-6789", journals, conferences, other)

    assert result["_meta"]["total_count"] == 1
    assert len(result["journal_articles"]) == 1
    assert result["conference_papers"] == []
    assert result["other_publications"] == []


def test_export_publications_title_keeps_markup():
    """Titles keep ORCID's markup; the composer renders it per format (owner, 2026-11-13)."""
    title = "<i>Italic</i> title with <sub>subscript</sub> and $\\alpha$"
    journals = [{"title": title, "year": "2024", "doi": "", "raw_authors": ["Smith"], "venue": "J"}]

    result = export_publications("0000-0001-2345-6789", journals, [], [])

    assert result["journal_articles"][0]["title"] == title


def test_export_publications_metadata_structure():
    """Test that metadata has required fields with correct types."""
    journals = [
        {"title": "Paper", "year": "2024", "doi": "", "raw_authors": ["Smith"], "venue": "J"}
    ]

    result = export_publications("0000-0001-2345-6789", journals, [], [])

    meta = result["_meta"]
    assert isinstance(meta["section"], str)
    assert isinstance(meta["orcid_id"], str)
    assert isinstance(meta["total_count"], int)
    assert isinstance(meta["generated_at"], str)

    # Verify timestamp format (ISO 8601 with timezone)
    timestamp = meta["generated_at"]
    # Should be parseable as ISO format
    datetime.fromisoformat(timestamp)  # Raises if invalid


def test_export_publications_preserves_all_fields():
    """Test that all publication fields are preserved in export."""
    journals = [
        {
            "title": "Title",
            "year": "2024",
            "doi": "10.1000/j1",
            "raw_authors": ["Smith, A."],
            "venue": "Nature",
            "extra": "data",
        },
    ]

    result = export_publications("0000-0001-2345-6789", journals, [], [])

    pub = result["journal_articles"][0]
    assert pub["year"] == "2024"
    assert pub["doi"] == "10.1000/j1"
    assert pub["raw_authors"] == ["Smith, A."]
    assert pub["venue"] == "Nature"
    # Extra fields should be preserved
    assert pub.get("extra") == "data"


# ── export_data ───────────────────────────────────────────────────────────


def test_export_data_all_fields():
    """Test export with all data fields populated."""
    biography = "Researcher at <b>Texas A&M</b>"
    external_ids = [{"type": "Scopus", "value": "123456"}]
    fundings = [
        {
            "title": "Grant",
            "organization": "NSF",
            "type": "grant",
            "start_year": "2022",
            "end_year": "2025",
        }
    ]
    employments = [
        {"organization": "TAMU", "role": "Professor", "department": "CS", "start_year": "2020"}
    ]
    educations = [
        {
            "organization": "MIT",
            "role": "PhD",
            "department": "EECS",
            "start_year": "2015",
            "end_year": "2020",
        }
    ]
    distinctions = [{"organization": "IEEE", "role": "Fellow", "start_year": "2022"}]
    memberships = [{"organization": "ACM", "role": "Member", "start_year": "2018"}]
    services = [{"organization": "IEEE Trans", "role": "Editor", "start_year": "2021"}]

    result = export_data(
        "0000-0001-2345-6789",
        biography,
        external_ids,
        fundings,
        employments,
        educations,
        distinctions,
        memberships,
        services,
    )

    assert result["_meta"]["section"] == "orcid-data"
    assert result["_meta"]["orcid_id"] == "0000-0001-2345-6789"
    assert "generated_at" in result["_meta"]

    # The biography keeps its markup; the composer renders it per format
    assert result["biography"] == "Researcher at <b>Texas A&M</b>"

    assert result["employment"] == employments
    assert result["education"] == educations
    assert result["distinctions"] == distinctions
    assert result["memberships"] == memberships
    assert result["external_service"] == services
    assert result["fundings"] == fundings
    assert result["external_identifiers"] == external_ids


def test_export_data_empty_returns_empty_dict():
    """Test that export with no data returns empty dict."""
    result = export_data("0000-0001-2345-6789", None, [], [], [], [], [], [], [])

    assert result == {}


def test_export_data_only_biography():
    """Test export with only biography present."""
    biography = "Researcher at University"

    result = export_data("0000-0001-2345-6789", biography, [], [], [], [], [], [], [])

    assert result["_meta"]["section"] == "orcid-data"
    assert result["biography"] == "Researcher at University"
    assert result["employment"] == []
    assert result["education"] == []


def test_export_data_partial_fields():
    """Test export with only some fields populated."""
    employments = [{"organization": "TAMU", "role": "Professor"}]
    educations = [{"organization": "MIT", "role": "PhD"}]

    result = export_data("0000-0001-2345-6789", None, [], [], employments, educations, [], [], [])

    assert result["biography"] is None
    assert result["employment"] == employments
    assert result["education"] == educations
    assert result["distinctions"] == []
    assert result["memberships"] == []
    assert result["external_service"] == []
    assert result["fundings"] == []
    assert result["external_identifiers"] == []


def test_export_data_biography_keeps_markup():
    """The composer renders the markup per format (owner, 2026-11-13)."""
    biography = "<i>Researcher</i> with <sub>2</sub> years experience at <b>TAMU</b>"

    result = export_data("0000-0001-2345-6789", biography, [], [], [], [], [], [], [])

    assert result["biography"] == biography


def test_export_data_biography_none():
    """Test handling of None biography."""
    result = export_data("0000-0001-2345-6789", None, [], [], [{"org": "TAMU"}], [], [], [], [])

    assert result["biography"] is None


def test_export_data_metadata_structure():
    """Test metadata structure for data export."""
    result = export_data("0000-0001-2345-6789", "Bio", [], [], [], [], [], [], [])

    meta = result["_meta"]
    assert meta["section"] == "orcid-data"
    assert isinstance(meta["orcid_id"], str)
    assert isinstance(meta["generated_at"], str)

    # Verify timestamp
    datetime.fromisoformat(meta["generated_at"])


# ── Entries are copies, as extracted ──────────────────────────────────────


def test_export_publications_copies_entries_unchanged():
    """Every field as extracted, markup included; the caller's dicts are not shared."""
    pub = {
        "title": "<i>Original</i>",
        "year": "2024",
        "doi": "10.1000/test",
        "raw_authors": ["Smith"],
    }

    result = export_publications("0000-0001-2345-6789", [pub], [], [])

    assert result["journal_articles"][0] == pub
    assert result["journal_articles"][0] is not pub


# ── Edge Cases ────────────────────────────────────────────────────────────


def test_export_publications_unicode_characters():
    """Test that Unicode characters in titles are preserved."""
    journals = [
        {
            "title": "Übersetzung of Résumé über Ångström",
            "year": "2024",
            "doi": "",
            "raw_authors": ["Schmidt"],
            "venue": "J",
        }
    ]

    result = export_publications("0000-0001-2345-6789", journals, [], [])

    title = result["journal_articles"][0]["title"]
    assert "Übersetzung" in title
    assert "Résumé" in title
    assert "Ångström" in title


def test_export_data_unicode_in_biography():
    """Test Unicode preservation in biography."""
    biography = "Researcher from Zürich studying Schrödinger equations"

    result = export_data("0000-0001-2345-6789", biography, [], [], [], [], [], [], [])

    assert "Zürich" in result["biography"]
    assert "Schrödinger" in result["biography"]


def test_export_publications_empty_strings():
    """Test handling of empty string fields."""
    journals = [{"title": "", "year": "", "doi": "", "raw_authors": [], "venue": ""}]

    result = export_publications("0000-0001-2345-6789", journals, [], [])

    # Should still export (has 1 publication)
    assert result["_meta"]["total_count"] == 1
    assert result["journal_articles"][0]["title"] == ""


def test_export_data_empty_biography_string():
    """Test handling of empty string biography."""
    biography = ""

    result = export_data(
        "0000-0001-2345-6789", biography, [], [], [{"org": "TAMU"}], [], [], [], []
    )

    # Empty string is falsy, but should be treated as no content for biography check
    # However, employments list is not empty, so export should happen
    assert result["biography"] == ""


def test_export_publications_provenance():
    """_meta.provenance: the keys tamu-scholars and academia-openalex write too."""
    journals = [{"title": "Paper", "year": "2024"}]
    result = export_publications(
        "0000-0001-2345-6789", journals, [], [], fetched_at="2026-11-13T00:00:00+00:00"
    )
    assert result["_meta"]["provenance"] == {
        "source": "orcid",
        "ids": ["0000-0001-2345-6789"],
        "curation": "author-curated",
        "fetched_at": "2026-11-13T00:00:00+00:00",
    }
    assert (
        export_publications("0000-0001-2345-6789", journals, [], [])["_meta"]["provenance"][
            "fetched_at"
        ]
        is None
    )
