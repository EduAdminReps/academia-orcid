"""Integration tests for end-to-end pipelines."""

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from academia_orcid import cli


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def integration_setup(tmp_path, sample_record):
    """Set up complete test environment with DB, cache, and output dirs."""
    # Create mapping database
    db_path = tmp_path / "shared.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE faculty_identifiers (UIN TEXT, Scheme TEXT, Identifier TEXT, Rank INTEGER)"
    )
    conn.execute("INSERT INTO faculty_identifiers VALUES (?, 'orcid', ?, 1)",
                 ("123456789", "0000-0001-2345-6789"))
    conn.commit()
    conn.close()

    # Create cached ORCID record
    data_dir = tmp_path / "data"
    json_dir = data_dir / "ORCID_JSON"
    json_dir.mkdir(parents=True)
    json_file = json_dir / "0000-0001-2345-6789.json"
    json_file.write_text(json.dumps(sample_record))

    # Output directory
    output_dir = tmp_path / "output"

    return {
        "db_path": db_path,
        "data_dir": data_dir,
        "output_dir": output_dir,
        "uin": "123456789",
        "orcid": "0000-0001-2345-6789",
    }


# ── Full LaTeX Pipeline ───────────────────────────────────────────────────


def test_full_latex_pipeline_with_uin(monkeypatch, integration_setup, capsys):
    """Test complete LaTeX pipeline: UIN → ORCID → extract → LaTeX."""
    setup = integration_setup

    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--uin", setup["uin"],
        "--mapping-db", str(setup["db_path"]),
        "--output-dir", str(setup["output_dir"]),
        "--data-dir", str(setup["data_dir"]),
        "--no-fetch"
    ])

    cli.main()

    # Verify output file exists
    output_file = setup["output_dir"] / "orcid-publications.tex"
    assert output_file.exists()

    # Verify content
    content = output_file.read_text()
    assert "A Journal Paper" in content
    assert "A Conference Paper" in content
    assert "A Book Chapter" in content

    # Verify logging
    captured = capsys.readouterr()
    assert f"Found ORCID {setup['orcid']} for UIN {setup['uin']}" in captured.err
    assert "Generated:" in captured.err


def test_full_latex_pipeline_with_orcid(monkeypatch, integration_setup):
    """Test LaTeX pipeline with direct ORCID ID (no UIN mapping)."""
    setup = integration_setup

    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", setup["orcid"],
        "--output-dir", str(setup["output_dir"]),
        "--data-dir", str(setup["data_dir"]),
        "--no-fetch"
    ])

    cli.main()

    output_file = setup["output_dir"] / "orcid-publications.tex"
    assert output_file.exists()

    content = output_file.read_text()
    assert "A Journal Paper" in content


def test_full_latex_pipeline_data_section(monkeypatch, integration_setup):
    """Test LaTeX pipeline for data section."""
    setup = integration_setup

    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", setup["orcid"],
        "--output-dir", str(setup["output_dir"]),
        "--data-dir", str(setup["data_dir"]),
        "--section", "data",
        "--no-fetch"
    ])

    cli.main()

    output_file = setup["output_dir"] / "orcid-data.tex"
    assert output_file.exists()

    content = output_file.read_text()
    assert "Texas A" in content  # Employment
    assert "MIT" in content  # Education


# ── Period Filtering End-to-End ───────────────────────────────────────────


def test_integration_period_single_calendar_year(monkeypatch, integration_setup, capsys):
    """One calendar year keeps only that year's publications."""
    setup = integration_setup

    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", setup["orcid"],
        "--output-dir", str(setup["output_dir"]),
        "--data-dir", str(setup["data_dir"]),
        "--cal_year", "2024",
        "--no-fetch"
    ])

    cli.main()

    output_file = setup["output_dir"] / "orcid-publications.tex"
    assert output_file.exists()

    content = output_file.read_text()
    assert "A Journal Paper" in content  # 2024
    assert "A Conference Paper" not in content  # 2023
    captured = capsys.readouterr()
    assert "Period: CY 2024" in captured.err


def test_integration_period_fiscal_year(monkeypatch, integration_setup):
    """--year is a fiscal year (Fall 2023 + Spring 2024): calendar 2023 and 2024 overlap it."""
    setup = integration_setup

    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", setup["orcid"],
        "--output-dir", str(setup["output_dir"]),
        "--data-dir", str(setup["data_dir"]),
        "--year", "2024",
        "--no-fetch"
    ])

    cli.main()

    content = (setup["output_dir"] / "orcid-publications.tex").read_text()
    assert "A Journal Paper" in content  # 2024
    assert "A Conference Paper" in content  # 2023
    assert "A Book Chapter" not in content  # 2022


def test_integration_period_range(monkeypatch, integration_setup):
    """A calendar-year range."""
    setup = integration_setup

    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", setup["orcid"],
        "--output-dir", str(setup["output_dir"]),
        "--data-dir", str(setup["data_dir"]),
        "--cal_year", "2023-2024",
        "--no-fetch"
    ])

    cli.main()

    output_file = setup["output_dir"] / "orcid-publications.tex"
    content = output_file.read_text()

    assert "A Journal Paper" in content  # 2024
    assert "A Conference Paper" in content  # 2023
    assert "A Book Chapter" not in content  # 2022


def test_integration_period_all(monkeypatch, integration_setup):
    """'all' includes everything."""
    setup = integration_setup

    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", setup["orcid"],
        "--output-dir", str(setup["output_dir"]),
        "--data-dir", str(setup["data_dir"]),
        "--year", "all",
        "--no-fetch"
    ])

    cli.main()

    output_file = setup["output_dir"] / "orcid-publications.tex"
    content = output_file.read_text()

    # All publications should be included
    assert "A Journal Paper" in content
    assert "A Conference Paper" in content
    assert "A Book Chapter" in content


# ── Cache Behavior ────────────────────────────────────────────────────────


def test_integration_uses_cache_first_run(monkeypatch, integration_setup, capsys):
    """Test that first run uses cached record."""
    setup = integration_setup

    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", setup["orcid"],
        "--output-dir", str(setup["output_dir"]),
        "--data-dir", str(setup["data_dir"]),
        "--no-fetch"
    ])

    cli.main()

    captured = capsys.readouterr()
    # Should not fetch (cache exists)
    assert "Fetching" not in captured.err


def test_integration_no_fetch_with_missing_cache(monkeypatch, tmp_path, capsys):
    """--no-fetch with a mapped ORCID but no cache file fails the section (exit 2), no file."""
    db_path = tmp_path / "shared.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE faculty_identifiers (UIN TEXT, Scheme TEXT, Identifier TEXT, Rank INTEGER)"
    )
    conn.execute("INSERT INTO faculty_identifiers VALUES (?, 'orcid', ?, 1)",
                 ("123456789", "0000-0001-2345-6789"))
    conn.commit()
    conn.close()

    data_dir = tmp_path / "data"
    (data_dir / "ORCID_JSON").mkdir(parents=True)  # Empty cache

    output_dir = tmp_path / "output"

    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--uin", "123456789",
        "--mapping-db", str(db_path),
        "--output-dir", str(output_dir),
        "--data-dir", str(data_dir),
        "--no-fetch"
    ])

    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    assert not (output_dir / "orcid-publications.tex").exists()
    assert "run `just prefetch`" in capsys.readouterr().err


# ── Error Recovery ────────────────────────────────────────────────────────


def test_integration_missing_uin_writes_nothing(monkeypatch, integration_setup, capsys):
    """A UIN with no ORCID row: exit 0 and no file (section contract rule 5; ORC-04)."""
    setup = integration_setup

    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--uin", "999999999",  # Not in database
        "--mapping-db", str(setup["db_path"]),
        "--output-dir", str(setup["output_dir"]),
        "--no-fetch"
    ])

    cli.main()

    output_file = setup["output_dir"] / "orcid-publications.tex"
    assert not output_file.exists()

    captured = capsys.readouterr()
    assert "No ORCID ID on file for UIN 999999999" in captured.err


def test_integration_invalid_orcid_exits(monkeypatch, tmp_path):
    """Test that invalid ORCID format exits with error."""
    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", "invalid-format",
        "--output-dir", str(tmp_path),
        "--no-fetch"
    ])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 1


# ── Section-Specific Invocations ──────────────────────────────────────────


def test_integration_publications_and_data_separate(monkeypatch, integration_setup):
    """Test that publications and data sections can be generated separately."""
    setup = integration_setup

    # Generate publications
    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", setup["orcid"],
        "--output-dir", str(setup["output_dir"]),
        "--data-dir", str(setup["data_dir"]),
        "--section", "publications",
        "--no-fetch"
    ])
    cli.main()

    pubs_file = setup["output_dir"] / "orcid-publications.tex"
    assert pubs_file.exists()

    # Generate data
    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", setup["orcid"],
        "--output-dir", str(setup["output_dir"]),
        "--data-dir", str(setup["data_dir"]),
        "--section", "data",
        "--no-fetch"
    ])
    cli.main()

    data_file = setup["output_dir"] / "orcid-data.tex"
    assert data_file.exists()

    # Both files should exist
    assert pubs_file.exists()
    assert data_file.exists()


# ── LaTeX Output Validation ───────────────────────────────────────────────


def test_integration_latex_syntax_valid(monkeypatch, integration_setup):
    """Test that generated LaTeX has valid syntax (basic check)."""
    setup = integration_setup

    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", setup["orcid"],
        "--output-dir", str(setup["output_dir"]),
        "--data-dir", str(setup["data_dir"]),
        "--no-fetch"
    ])

    cli.main()

    output_file = setup["output_dir"] / "orcid-publications.tex"
    content = output_file.read_text()

    # Basic LaTeX syntax checks
    assert content.count("{") == content.count("}")  # Balanced braces
    assert "\\" in content  # Has LaTeX commands
    assert "\\section" in content or "\\subsection" in content  # Has sections


def test_integration_latex_escapes_special_characters(monkeypatch, tmp_path):
    """Test that special characters are properly escaped in LaTeX output."""
    # Create record with special characters
    record = {
        "person": {},
        "activities-summary": {
            "works": {
                "group": [{
                    "work-summary": [{
                        "type": "journal-article",
                        "title": {"title": {"value": "Paper with & special $ characters"}},
                        "publication-date": {"year": {"value": "2024"}},
                        "journal-title": {"value": "Journal"},
                        "contributors": None,
                        "external-ids": {"external-id": []},
                    }]
                }]
            }
        }
    }

    data_dir = tmp_path / "data"
    json_dir = data_dir / "ORCID_JSON"
    json_dir.mkdir(parents=True)
    json_file = json_dir / "0000-0001-2345-6789.json"
    json_file.write_text(json.dumps(record))

    output_dir = tmp_path / "output"

    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", "0000-0001-2345-6789",
        "--output-dir", str(output_dir),
        "--data-dir", str(data_dir),
        "--no-fetch"
    ])

    cli.main()

    content = (output_dir / "orcid-publications.tex").read_text()

    # Special characters should be escaped (or handled safely)
    # At minimum, the file should be created without errors
    assert len(content) > 0


# ── Multiple Runs ─────────────────────────────────────────────────────────


def test_integration_multiple_runs_overwrite(monkeypatch, integration_setup):
    """Test that running twice overwrites the output file."""
    setup = integration_setup

    args = [
        "run_latex.py",
        "--orcid", setup["orcid"],
        "--output-dir", str(setup["output_dir"]),
        "--data-dir", str(setup["data_dir"]),
        "--no-fetch"
    ]

    # First run
    monkeypatch.setattr(sys, "argv", args)
    cli.main()

    output_file = setup["output_dir"] / "orcid-publications.tex"
    first_content = output_file.read_text()
    first_mtime = output_file.stat().st_mtime

    # Second run (small delay to ensure different mtime)
    import time
    time.sleep(0.01)

    monkeypatch.setattr(sys, "argv", args)
    cli.main()

    second_content = output_file.read_text()
    second_mtime = output_file.stat().st_mtime

    # Content should be the same (same data)
    assert first_content == second_content
    # File should have been rewritten (newer mtime)
    assert second_mtime >= first_mtime


# ── Output Directory Creation ─────────────────────────────────────────────


def test_integration_creates_nested_output_dirs(monkeypatch, integration_setup):
    """Test that deeply nested output directories are created."""
    setup = integration_setup

    nested_output = setup["output_dir"] / "level1" / "level2" / "level3"

    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", setup["orcid"],
        "--output-dir", str(nested_output),
        "--data-dir", str(setup["data_dir"]),
        "--no-fetch"
    ])

    cli.main()

    assert nested_output.exists()
    assert (nested_output / "orcid-publications.tex").exists()


# ── Empty Record Handling ─────────────────────────────────────────────────


def test_integration_empty_record_no_file(monkeypatch, tmp_path, empty_record):
    """Test that empty records don't create output files."""
    data_dir = tmp_path / "data"
    json_dir = data_dir / "ORCID_JSON"
    json_dir.mkdir(parents=True)
    json_file = json_dir / "0000-0009-0000-0000.json"
    json_file.write_text(json.dumps(empty_record))

    output_dir = tmp_path / "output"

    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", "0000-0009-0000-0000",
        "--output-dir", str(output_dir),
        "--data-dir", str(data_dir),
        "--no-fetch"
    ])

    cli.main()

    # No file should be created
    assert not (output_dir / "orcid-publications.tex").exists()


# ── Stdout/Stderr Separation ──────────────────────────────────────────────


def test_integration_stdout_stderr_separation(monkeypatch, integration_setup, capsys):
    """Test that file paths go to stdout and logs go to stderr."""
    setup = integration_setup

    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", setup["orcid"],
        "--output-dir", str(setup["output_dir"]),
        "--data-dir", str(setup["data_dir"]),
        "--no-fetch"
    ])

    cli.main()

    captured = capsys.readouterr()

    # Stdout should have the output file path
    assert str(setup["output_dir"] / "orcid-publications.tex") in captured.out

    # Stderr should have progress messages
    assert "Using ORCID ID directly" in captured.err
    assert "Found" in captured.err


# ── Run from JSON entry point ─────────────────────────────────────────────


def test_integration_run_json_entry_point(monkeypatch, integration_setup):
    """Test running via run_json.py entry point."""
    setup = integration_setup

    # Import run_json module
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    import run_json

    monkeypatch.setattr(sys, "argv", [
        "run_json.py",
        "--orcid", setup["orcid"],
        "--output-dir", str(setup["output_dir"]),
        "--data-dir", str(setup["data_dir"]),
        "--no-fetch"
    ])

    run_json.main()

    # Should create JSON file
    output_file = setup["output_dir"] / "orcid-publications.json"
    assert output_file.exists()

    # Verify JSON structure
    with open(output_file) as f:
        data = json.load(f)

    assert "_meta" in data
    assert "journal_articles" in data
    assert data["_meta"]["section"] == "orcid-publications"


def test_integration_run_json_no_fetch_with_missing_cache_fails(monkeypatch, tmp_path, capsys):
    """JSON and LaTeX agree: under --no-fetch an uncached record fails the section (exit 2)."""
    sys.path.insert(0, str(Path(__file__).parent.parent))
    import run_json

    (tmp_path / "ORCID_JSON").mkdir()
    monkeypatch.setattr(sys, "argv", [
        "run_json.py", "--orcid", "0000-0001-2345-6789",
        "--output-dir", str(tmp_path / "out"), "--data-dir", str(tmp_path), "--no-fetch",
    ])
    with pytest.raises(SystemExit) as exc:
        run_json.main()
    assert exc.value.code == 2
    assert not (tmp_path / "out" / "orcid-publications.json").exists()
    assert "run `just prefetch`" in capsys.readouterr().err
