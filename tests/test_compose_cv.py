"""Tests for the standalone CV composer (tools/compose_cv.py)."""

import sys
from pathlib import Path

import pytest

# Ensure tools/ is importable
_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(_TOOLS_DIR))

from compose_cv import extract_person_info


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def record_with_name():
    """An ORCID record with person name and current employment."""
    return {
        "person": {
            "name": {
                "given-names": {"value": "Alice"},
                "family-name": {"value": "Smith"},
            },
            "biography": {
                "content": "Researcher at Texas A&M University.",
            },
        },
        "activities-summary": {
            "employments": {
                "affiliation-group": [{
                    "summaries": [{
                        "employment-summary": {
                            "organization": {
                                "name": "Texas A&M University",
                                "address": {"city": "College Station", "region": "", "country": "US"},
                            },
                            "role-title": "Professor",
                            "department-name": "Electrical Engineering",
                            "start-date": {"year": {"value": "2015"}},
                            "end-date": None,
                        }
                    }]
                }],
            },
            "works": {"group": []},
        },
    }


@pytest.fixture
def record_no_name():
    """An ORCID record with no person name."""
    return {
        "person": {},
        "activities-summary": {},
    }


@pytest.fixture
def record_no_employment():
    """An ORCID record with name but no employment."""
    return {
        "person": {
            "name": {
                "given-names": {"value": "Bob"},
                "family-name": {"value": "Jones"},
            },
        },
        "activities-summary": {},
    }


# ---------------------------------------------------------------------------
# Tests: extract_person_info
# ---------------------------------------------------------------------------

class TestExtractPersonInfo:
    """Test person info extraction from ORCID records."""

    def test_full_record(self, record_with_name):
        info = extract_person_info(record_with_name)
        assert info["name"] == "Alice Smith"
        assert info["institution"] == "Texas A&M University"
        assert info["department"] == "Electrical Engineering"

    def test_no_name(self, record_no_name):
        info = extract_person_info(record_no_name)
        assert info["name"] == "Unknown"
        assert info["institution"] == ""
        assert info["department"] == ""

    def test_no_employment(self, record_no_employment):
        info = extract_person_info(record_no_employment)
        assert info["name"] == "Bob Jones"
        assert info["institution"] == ""
        assert info["department"] == ""

    def test_with_sample_record(self, sample_record):
        """Test with the shared sample_record fixture (has employment but no name field)."""
        info = extract_person_info(sample_record)
        # sample_record has no person.name, so falls back to "Unknown"
        assert info["name"] == "Unknown"
        # But it has employment data
        assert info["institution"] == "Texas A&M University"
        assert info["department"] == "Electrical Engineering"


# ---------------------------------------------------------------------------
# Tests: LaTeX pipeline (file generation)
# ---------------------------------------------------------------------------

class TestLatexPipeline:
    """Test LaTeX CV generation (without compilation)."""

    def test_generates_all_files(self, record_with_name, tmp_path):
        """Verify that the LaTeX pipeline creates all expected files."""
        from compose_cv import (
            TEMPLATES_DIR,
            create_source_archive,
            escape_latex,
            extract_person_info,
            generate_header,
            generate_main,
        )
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
        )
        from academia_orcid.latex import generate_data_latex, generate_latex
        import shutil

        output_dir = tmp_path / "output"
        output_dir.mkdir()
        orcid_id = "0000-0001-2345-6789"

        # Copy preamble
        shutil.copy(TEMPLATES_DIR / "preamble.tex", output_dir / "preamble.tex")

        # Generate header
        person = extract_person_info(record_with_name)
        faculty_info = {
            "name": escape_latex(person["name"]),
            "department": "",
            "department_name": escape_latex(person["department"]),
            "title": "",
            "identifier_label": "ORCID",
            "identifier_value": orcid_id,
            "institution": escape_latex(person["institution"]),
            "college": "",
        }
        generate_header(faculty_info, TEMPLATES_DIR / "header.tex.template",
                        output_dir / "header.tex")

        # Generate data section
        biography = extract_biography(record_with_name)
        ext_ids = extract_external_identifiers(record_with_name)
        fundings = extract_fundings(record_with_name)
        employments = extract_employments(record_with_name)
        educations = extract_educations(record_with_name)
        distinctions = extract_distinctions(record_with_name)
        memberships = extract_memberships(record_with_name)
        services = extract_services(record_with_name)

        data_latex = generate_data_latex(
            orcid_id, biography, ext_ids, fundings,
            employments, educations, distinctions, memberships, services
        )
        if data_latex:
            (output_dir / "orcid-data.tex").write_text(data_latex)

        # Generate publications section
        journal, conf, other = extract_publications(record_with_name)
        pubs_latex = generate_latex(orcid_id, journal, conf, other)
        if pubs_latex:
            (output_dir / "orcid-publications.tex").write_text(pubs_latex)

        # Generate main.tex
        generate_main("All Years", TEMPLATES_DIR / "main.tex.template",
                      output_dir / "main.tex")

        # Verify files exist
        assert (output_dir / "preamble.tex").exists()
        assert (output_dir / "header.tex").exists()
        assert (output_dir / "main.tex").exists()

        # Verify header content
        header_content = (output_dir / "header.tex").read_text()
        assert "Alice Smith" in header_content
        assert "Electrical Engineering" in header_content
        assert "ORCID" in header_content
        assert orcid_id in header_content

        # Verify main.tex structure
        main_content = (output_dir / "main.tex").read_text()
        assert r"\begin{document}" in main_content
        assert r"\end{document}" in main_content
        assert r"\input{header}" in main_content
        assert "orcid-data.tex" in main_content
        assert "orcid-publications.tex" in main_content

        # Source archive
        zip_path = create_source_archive(output_dir, orcid_id)
        assert zip_path.exists()
        assert zip_path.suffix == ".zip"


# ---------------------------------------------------------------------------
# Tests: DOCX pipeline
# ---------------------------------------------------------------------------

class TestDocxPipeline:
    """Test DOCX CV generation."""

    def test_generates_docx(self, record_with_name, tmp_path):
        """Verify that the DOCX pipeline creates a valid document."""
        pytest.importorskip("docx")

        from docx_formatter import OrcidDocxFormatter
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
        )
        from academia_orcid.json_export import export_data, export_publications
        from datetime import datetime, timezone

        output_dir = tmp_path / "docx_output"
        orcid_id = "0000-0001-2345-6789"

        person = extract_person_info(record_with_name)

        # Extract data
        biography = extract_biography(record_with_name)
        ext_ids = extract_external_identifiers(record_with_name)
        fundings = extract_fundings(record_with_name)
        employments = extract_employments(record_with_name)
        educations = extract_educations(record_with_name)
        distinctions = extract_distinctions(record_with_name)
        memberships = extract_memberships(record_with_name)
        services = extract_services(record_with_name)

        journal, conf, other = extract_publications(record_with_name)

        data_json = export_data(
            orcid_id, biography, ext_ids, fundings,
            employments, educations, distinctions, memberships, services
        )
        pubs_json = export_publications(orcid_id, journal, conf, other)

        profile = {
            "_meta": {
                "uin": orcid_id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "year_filter": None,
            },
            "identity": {
                "name": person["name"],
                "department_name": person["department"],
                "identifier_label": "ORCID",
                "identifier_value": orcid_id,
                "institution": person["institution"],
                "college": "",
            },
        }
        if data_json:
            profile["orcid_data"] = data_json
        if pubs_json:
            profile["orcid_publications"] = pubs_json

        formatter = OrcidDocxFormatter()
        paths = formatter.format(profile, output_dir)

        assert len(paths) == 1
        assert paths[0].exists()
        assert paths[0].suffix == ".docx"
        assert orcid_id in paths[0].name

        # Verify it's a valid DOCX by opening it
        from docx import Document
        doc = Document(str(paths[0]))
        # Should have content (at least the header paragraphs)
        assert len(doc.paragraphs) > 0

    def test_empty_profile(self, tmp_path):
        """DOCX generation with no ORCID data sections."""
        pytest.importorskip("docx")

        from docx_formatter import OrcidDocxFormatter
        from datetime import datetime, timezone

        output_dir = tmp_path / "docx_empty"
        orcid_id = "0000-0001-0000-0000"

        profile = {
            "_meta": {
                "uin": orcid_id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "year_filter": None,
            },
            "identity": {
                "name": "Test Faculty",
                "department_name": "",
                "identifier_label": "ORCID",
                "identifier_value": orcid_id,
                "institution": "",
                "college": "",
            },
        }

        formatter = OrcidDocxFormatter()
        paths = formatter.format(profile, output_dir)
        assert len(paths) == 1
        assert paths[0].exists()
