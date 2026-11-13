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
                "affiliation-group": [
                    {
                        "summaries": [
                            {
                                "employment-summary": {
                                    "organization": {
                                        "name": "Texas A&M University",
                                        "address": {
                                            "city": "College Station",
                                            "region": "",
                                            "country": "US",
                                        },
                                    },
                                    "role-title": "Professor",
                                    "department-name": "Electrical Engineering",
                                    "start-date": {"year": {"value": "2015"}},
                                    "end-date": None,
                                }
                            }
                        ]
                    }
                ],
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
        import shutil

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
        generate_header(
            faculty_info, TEMPLATES_DIR / "header.tex.template", output_dir / "header.tex"
        )

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
            orcid_id,
            biography,
            ext_ids,
            fundings,
            employments,
            educations,
            distinctions,
            memberships,
            services,
        )
        if data_latex:
            (output_dir / "orcid-data.tex").write_text(data_latex)

        # Generate publications section
        journal, conf, other = extract_publications(record_with_name)
        pubs_latex = generate_latex(orcid_id, journal, conf, other)
        if pubs_latex:
            (output_dir / "orcid-publications.tex").write_text(pubs_latex)

        # Generate main.tex
        generate_main("All Years", TEMPLATES_DIR / "main.tex.template", output_dir / "main.tex")

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
# Tests: whole runs (main), reruns into the same directory (audit ORC-08, ORC-15)
# ---------------------------------------------------------------------------

ORCID = "0000-0001-2345-6789"


@pytest.fixture
def cached(tmp_path, sample_record):
    """A data dir with sample_record cached (publications dated 2022-2024)."""
    import json

    (tmp_path / "ORCID_JSON").mkdir()
    (tmp_path / "ORCID_JSON" / f"{ORCID}.json").write_text(json.dumps(sample_record))
    return tmp_path


def _run(data_dir, out_dir, *extra):
    from compose_cv import main

    main(
        [
            "--orcid",
            ORCID,
            "--data-dir",
            str(data_dir),
            "--output-dir",
            str(out_dir),
            "--no-fetch",
            "--skip-compile",
            *extra,
        ]
    )


class TestComposeRuns:
    def test_rerun_for_an_empty_period_drops_the_old_publications(self, cached, tmp_path):
        out = tmp_path / "out"
        _run(cached, out)
        assert (out / "orcid-publications.tex").exists()
        assert (out / "orcid-publications-summary.tex").exists()

        _run(cached, out, "--cal_year", "2099")
        assert not (out / "orcid-publications.tex").exists()
        assert not (out / "orcid-publications-summary.tex").exists()
        assert "CY 2099" in (out / "main.tex").read_text()

    def test_other_files_in_the_output_dir_are_kept(self, cached, tmp_path):
        out = tmp_path / "shared"
        out.mkdir()
        for name in ("thesis.pdf", "photos.zip", "notes.log"):
            (out / name).write_text("keep me")
        _run(cached, out)
        _run(cached, out)
        for name in ("thesis.pdf", "photos.zip", "notes.log"):
            assert (out / name).read_text() == "keep me"

    def test_archive_holds_only_this_runs_sources(self, cached, tmp_path):
        import zipfile

        out = tmp_path / "out"
        out.mkdir()
        (out / "unrelated.txt").write_text("x")
        _run(cached, out)
        names = set(zipfile.ZipFile(out / f"{ORCID}-source.zip").namelist())
        assert "unrelated.txt" not in names
        assert {"main.tex", "header.tex", "preamble.tex", "orcid-publications.tex"} <= names

    def test_template_writes_the_headings(self, cached, tmp_path):
        out = tmp_path / "out"
        _run(cached, out)
        main_tex = (out / "main.tex").read_text()
        assert r"\section{ORCID Data}" in main_tex
        assert r"\section{ORCID Publications}" in main_tex
        assert r"\input{orcid-publications-summary}" in main_tex
        for name in ("orcid-data.tex", "orcid-publications.tex", "orcid-publications-summary.tex"):
            assert r"\section{" not in (out / name).read_text()

    def test_not_cached_under_no_fetch_exits_2(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            _run(tmp_path, tmp_path / "out")
        assert exc.value.code == 2

    def test_fetch_error_exits_2(self, tmp_path, monkeypatch):
        import compose_cv

        from academia_orcid.fetch import OrcidFetchError

        def fail(*_args, **_kwargs):
            raise OrcidFetchError("HTTP 503")

        monkeypatch.setattr(compose_cv, "get_or_fetch_orcid_record", fail)
        with pytest.raises(SystemExit) as exc:
            compose_cv.main(
                [
                    "--orcid",
                    ORCID,
                    "--data-dir",
                    str(tmp_path),
                    "--output-dir",
                    str(tmp_path / "out"),
                    "--skip-compile",
                ]
            )
        assert exc.value.code == 2

    def test_docx_is_retired(self, cached, tmp_path):
        with pytest.raises(SystemExit) as exc:
            _run(cached, tmp_path / "out", "--format", "docx")
        assert exc.value.code == 2  # argparse: invalid choice

    def test_logs_reach_the_configured_handler(self, cached, tmp_path, capsys):
        _run(cached, tmp_path / "out")
        assert "Created: orcid-publications.tex" in capsys.readouterr().err

    def test_bibtex_rerun_for_an_empty_period_drops_the_old_file(self, cached, tmp_path):
        out = tmp_path / "out"
        _run(cached, out, "--format", "bibtex")
        assert (out / f"{ORCID}.bib").exists()
        _run(cached, out, "--format", "bibtex", "--cal_year", "2099")
        assert not (out / f"{ORCID}.bib").exists()


# ---------------------------------------------------------------------------
# Tests: BibTeX pipeline
# ---------------------------------------------------------------------------


class TestBibtexPipeline:
    """Test BibTeX CV generation."""

    def test_generates_bib_file(self, sample_record, tmp_path):
        """Verify that the BibTeX pipeline creates a valid .bib file."""
        from academia_orcid.bibtex_export import export_bibtex
        from academia_orcid.extract import extract_publications

        output_dir = tmp_path / "bibtex_output"
        output_dir.mkdir()
        orcid_id = "0000-0001-2345-6789"

        journal, conf, other = extract_publications(sample_record)
        bibtex_content = export_bibtex(orcid_id, journal, conf, other)

        assert bibtex_content  # should have content
        bib_path = output_dir / f"{orcid_id}.bib"
        bib_path.write_text(bibtex_content, encoding="utf-8")

        assert bib_path.exists()
        content = bib_path.read_text()
        assert f"% BibTeX export from ORCID record: {orcid_id}" in content
        assert "@article{" in content  # journal article
        assert "@inproceedings{" in content  # conference paper

    def test_empty_record(self, tmp_path):
        """BibTeX export with no publications returns empty string."""
        from academia_orcid.bibtex_export import export_bibtex

        result = export_bibtex("0000-0001-0000-0000", [], [], [])
        assert result == ""

    def test_period_filter_applied(self, sample_record):
        """The period filter works with BibTeX export pipeline."""
        from academia_orcid.bibtex_export import export_bibtex
        from academia_orcid.extract import (
            extract_publications,
            filter_publications_by_period,
        )
        from academia_orcid.periods import period_from_flag

        journal, conf, other = extract_publications(sample_record)

        # Calendar 2024 only (should keep journal article, exclude 2023 and 2022)
        period = period_from_flag("cal_year", "2024")
        journal = filter_publications_by_period(journal, period)
        conf = filter_publications_by_period(conf, period)
        other = filter_publications_by_period(other, period)

        result = export_bibtex("0000-0001-2345-6789", journal, conf, other)
        assert "% Entries: 1 total" in result
        assert "@article{" in result
        assert "@inproceedings{" not in result
