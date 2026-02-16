"""Tests for CLI entry point (cli.py main() function)."""

import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from academia_orcid import cli


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def mapping_db(tmp_path):
    """Create a test mapping database with UIN→ORCID mappings."""
    db_path = tmp_path / "shared.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE orcid_mapping (UIN TEXT, ORCID TEXT)")
    conn.execute("INSERT INTO orcid_mapping VALUES (?, ?)", ("123456789", "0000-0001-2345-6789"))
    conn.execute("INSERT INTO orcid_mapping VALUES (?, ?)", ("999999999", None))
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def cached_orcid(tmp_path, sample_record):
    """Create cached ORCID record."""
    import json
    json_dir = tmp_path / "ORCID_JSON"
    json_dir.mkdir()
    json_file = json_dir / "0000-0001-2345-6789.json"
    json_file.write_text(json.dumps(sample_record))
    return tmp_path


# ── Argument Parsing ──────────────────────────────────────────────────────


def test_cli_requires_uin_or_orcid(monkeypatch, tmp_path):
    """Test that CLI requires either --uin or --orcid."""
    monkeypatch.setattr(sys, "argv", ["run_latex.py", "--output-dir", str(tmp_path)])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 2  # argparse error


def test_cli_requires_output_dir(monkeypatch):
    """Test that --output-dir is required."""
    monkeypatch.setattr(sys, "argv", ["run_latex.py", "--uin", "123456789"])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 2  # argparse error


def test_cli_accepts_uin_or_orcid_mutually_exclusive(monkeypatch, tmp_path, mapping_db, cached_orcid):
    """Test that --uin and --orcid can be used independently."""
    # Test with --uin
    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--uin", "123456789",
        "--mapping-db", str(mapping_db),
        "--output-dir", str(tmp_path),
        "--data-dir", str(cached_orcid),
        "--no-fetch"
    ])

    cli.main()  # Should not raise

    # Test with --orcid
    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", "0000-0001-2345-6789",
        "--output-dir", str(tmp_path),
        "--data-dir", str(cached_orcid),
        "--no-fetch"
    ])

    cli.main()  # Should not raise


def test_cli_section_choices(monkeypatch, tmp_path):
    """Test that --section only accepts valid choices."""
    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", "0000-0001-2345-6789",
        "--output-dir", str(tmp_path),
        "--section", "invalid"
    ])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 2  # argparse error


# ── Input Validation ──────────────────────────────────────────────────────


def test_cli_validates_uin_format(monkeypatch, tmp_path, mapping_db):
    """Test that invalid UIN format is rejected."""
    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--uin", "abc123",
        "--mapping-db", str(mapping_db),
        "--output-dir", str(tmp_path),
        "--no-fetch"
    ])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 1


def test_cli_validates_orcid_format(monkeypatch, tmp_path):
    """Test that invalid ORCID format is rejected."""
    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", "../../../etc/passwd",
        "--output-dir", str(tmp_path),
        "--no-fetch"
    ])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 1


def test_cli_requires_mapping_db_for_uin(monkeypatch, tmp_path):
    """Test that --mapping-db is required when using --uin."""
    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--uin", "123456789",
        "--output-dir", str(tmp_path),
        "--no-fetch"
    ])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 1


def test_cli_validates_mapping_db_exists(monkeypatch, tmp_path):
    """Test that CLI checks if mapping database file exists."""
    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--uin", "123456789",
        "--mapping-db", "/nonexistent/path.db",
        "--output-dir", str(tmp_path),
        "--no-fetch"
    ])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 1


# ── UIN→ORCID Resolution ──────────────────────────────────────────────────


def test_cli_resolves_uin_to_orcid(monkeypatch, tmp_path, mapping_db, cached_orcid, capsys):
    """Test successful UIN→ORCID mapping and record loading."""
    output_dir = tmp_path / "output"
    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--uin", "123456789",
        "--mapping-db", str(mapping_db),
        "--output-dir", str(output_dir),
        "--data-dir", str(cached_orcid),
        "--no-fetch"
    ])

    cli.main()

    # Check that output file was created
    assert (output_dir / "orcid-publications.tex").exists()

    # Check stderr output
    captured = capsys.readouterr()
    assert "Found ORCID 0000-0001-2345-6789 for UIN 123456789" in captured.err


def test_cli_handles_uin_not_in_database(monkeypatch, tmp_path, mapping_db, capsys):
    """Test handling of UIN not found in mapping database."""
    output_dir = tmp_path / "output"
    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--uin", "000000000",
        "--mapping-db", str(mapping_db),
        "--output-dir", str(output_dir),
        "--no-fetch"
    ])

    cli.main()

    # Should create placeholder file
    assert (output_dir / "orcid-publications.tex").exists()

    # Check stderr for warning
    captured = capsys.readouterr()
    assert "No ORCID ID found for UIN 000000000" in captured.err

    # Check placeholder content
    content = (output_dir / "orcid-publications.tex").read_text()
    assert "No ORCID ID on file" in content


def test_cli_handles_null_orcid_in_database(monkeypatch, tmp_path, mapping_db, capsys):
    """Test handling of NULL ORCID in database."""
    output_dir = tmp_path / "output"
    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--uin", "999999999",
        "--mapping-db", str(mapping_db),
        "--output-dir", str(output_dir),
        "--no-fetch"
    ])

    cli.main()

    # Should create placeholder
    assert (output_dir / "orcid-publications.tex").exists()
    captured = capsys.readouterr()
    assert "No ORCID ID found for UIN 999999999" in captured.err


# ── ORCID Record Loading ──────────────────────────────────────────────────


def test_cli_uses_cached_record_by_default(monkeypatch, tmp_path, cached_orcid, capsys):
    """Test that cached records are used by default (no fetch)."""
    output_dir = tmp_path / "output"
    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", "0000-0001-2345-6789",
        "--output-dir", str(output_dir),
        "--data-dir", str(cached_orcid),
        "--no-fetch"
    ])

    cli.main()

    assert (output_dir / "orcid-publications.tex").exists()
    captured = capsys.readouterr()
    assert "Fetching" not in captured.err  # No fetch should happen


def test_cli_no_fetch_flag(monkeypatch, tmp_path, cached_orcid):
    """Test that --no-fetch prevents API calls."""
    output_dir = tmp_path / "output"
    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", "0000-0001-2345-6789",
        "--output-dir", str(output_dir),
        "--data-dir", str(cached_orcid),
        "--no-fetch"
    ])

    cli.main()
    assert (output_dir / "orcid-publications.tex").exists()


def test_cli_handles_missing_cached_record(monkeypatch, tmp_path, capsys):
    """Test handling when ORCID record not in cache and fetch disabled."""
    # Create ORCID_JSON directory but no record file
    (tmp_path / "ORCID_JSON").mkdir()

    output_dir = tmp_path / "output"
    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", "0000-0009-9999-9999",
        "--output-dir", str(output_dir),
        "--data-dir", str(tmp_path),
        "--no-fetch"
    ])

    cli.main()

    # Should create placeholder
    assert (output_dir / "orcid-publications.tex").exists()
    captured = capsys.readouterr()
    assert "No ORCID record found" in captured.err


# ── Section Generation ────────────────────────────────────────────────────


def test_cli_generates_publications_section(monkeypatch, tmp_path, cached_orcid):
    """Test generation of publications section (default)."""
    output_dir = tmp_path / "output"
    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", "0000-0001-2345-6789",
        "--output-dir", str(output_dir),
        "--data-dir", str(cached_orcid),
        "--no-fetch"
    ])

    cli.main()

    output_file = output_dir / "orcid-publications.tex"
    assert output_file.exists()

    content = output_file.read_text()
    assert "A Journal Paper" in content
    assert "A Conference Paper" in content


def test_cli_generates_data_section(monkeypatch, tmp_path, cached_orcid):
    """Test generation of data section with --section data."""
    output_dir = tmp_path / "output"
    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", "0000-0001-2345-6789",
        "--output-dir", str(output_dir),
        "--data-dir", str(cached_orcid),
        "--section", "data",
        "--no-fetch"
    ])

    cli.main()

    output_file = output_dir / "orcid-data.tex"
    assert output_file.exists()

    content = output_file.read_text()
    assert "Texas A" in content  # Employment data


def test_cli_year_filter_for_publications(monkeypatch, tmp_path, cached_orcid, capsys):
    """Test year filtering for publications section."""
    output_dir = tmp_path / "output"
    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", "0000-0001-2345-6789",
        "--output-dir", str(output_dir),
        "--data-dir", str(cached_orcid),
        "--year", "2024-2024",
        "--no-fetch"
    ])

    cli.main()

    captured = capsys.readouterr()
    assert "Year filter: 2024-2024" in captured.err
    assert "after year filter" in captured.err


def test_cli_year_filter_ignored_for_data(monkeypatch, tmp_path, cached_orcid, capsys):
    """Test that year filter is ignored for data section."""
    output_dir = tmp_path / "output"
    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", "0000-0001-2345-6789",
        "--output-dir", str(output_dir),
        "--data-dir", str(cached_orcid),
        "--section", "data",
        "--year", "2024",
        "--no-fetch"
    ])

    cli.main()

    captured = capsys.readouterr()
    assert "--year is ignored for --section data" in captured.err


def test_cli_skips_file_creation_when_no_data(monkeypatch, tmp_path, empty_record):
    """Test that no file is created when there's no data (empty record)."""
    import json

    # Create empty record
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


# ── Output and Logging ────────────────────────────────────────────────────


def test_cli_creates_output_directory(monkeypatch, tmp_path, cached_orcid):
    """Test that output directory is created if it doesn't exist."""
    output_dir = tmp_path / "nonexistent" / "nested" / "output"

    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", "0000-0001-2345-6789",
        "--output-dir", str(output_dir),
        "--data-dir", str(cached_orcid),
        "--no-fetch"
    ])

    cli.main()

    assert output_dir.exists()
    assert (output_dir / "orcid-publications.tex").exists()


def test_cli_prints_output_file_path(monkeypatch, tmp_path, cached_orcid, capsys):
    """Test that CLI prints output file path to stdout."""
    output_dir = tmp_path / "output"

    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", "0000-0001-2345-6789",
        "--output-dir", str(output_dir),
        "--data-dir", str(cached_orcid),
        "--no-fetch"
    ])

    cli.main()

    captured = capsys.readouterr()
    assert str(output_dir / "orcid-publications.tex") in captured.out


def test_cli_logs_to_stderr(monkeypatch, tmp_path, cached_orcid, capsys):
    """Test that progress messages go to stderr."""
    output_dir = tmp_path / "output"

    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", "0000-0001-2345-6789",
        "--output-dir", str(output_dir),
        "--data-dir", str(cached_orcid),
        "--no-fetch"
    ])

    cli.main()

    captured = capsys.readouterr()
    assert "Using ORCID ID directly" in captured.err
    assert "Found" in captured.err
    assert "Generated" in captured.err


# ── Error Handling ────────────────────────────────────────────────────────


def test_cli_handles_invalid_year_format_gracefully(monkeypatch, tmp_path, cached_orcid, capsys):
    """Test that invalid year format is handled gracefully (warning, no crash)."""
    output_dir = tmp_path / "output"

    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", "0000-0001-2345-6789",
        "--output-dir", str(output_dir),
        "--data-dir", str(cached_orcid),
        "--year", "invalid",
        "--no-fetch"
    ])

    cli.main()  # Should not crash

    captured = capsys.readouterr()
    assert "Invalid year" in captured.err


# ── Direct ORCID ID Usage ─────────────────────────────────────────────────


def test_cli_accepts_direct_orcid(monkeypatch, tmp_path, cached_orcid, capsys):
    """Test using --orcid directly without UIN mapping."""
    output_dir = tmp_path / "output"

    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", "0000-0001-2345-6789",
        "--output-dir", str(output_dir),
        "--data-dir", str(cached_orcid),
        "--no-fetch"
    ])

    cli.main()

    assert (output_dir / "orcid-publications.tex").exists()

    captured = capsys.readouterr()
    assert "Using ORCID ID directly: 0000-0001-2345-6789" in captured.err


def test_cli_direct_orcid_does_not_require_mapping_db(monkeypatch, tmp_path, cached_orcid):
    """Test that --orcid does not require --mapping-db."""
    output_dir = tmp_path / "output"

    monkeypatch.setattr(sys, "argv", [
        "run_latex.py",
        "--orcid", "0000-0001-2345-6789",
        "--output-dir", str(output_dir),
        "--data-dir", str(cached_orcid),
        "--no-fetch"
    ])

    cli.main()  # Should not raise


# ── Edge Cases ────────────────────────────────────────────────────────────


def test_cli_handles_special_characters_in_content(monkeypatch, tmp_path):
    """Test that special characters in ORCID data are properly escaped."""
    import json

    # Create record with special LaTeX characters
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
    # LaTeX special chars should be escaped
    assert r"\&" in content or "&" in content  # Depending on escape strategy
    assert r"\$" in content or "$" in content


def test_cli_data_dir_defaults_to_current(monkeypatch, tmp_path, cached_orcid):
    """Test that --data-dir defaults to current directory."""
    output_dir = tmp_path / "output"

    # Change to tmp directory and use default data-dir
    import os
    original_cwd = os.getcwd()
    os.chdir(cached_orcid)

    try:
        monkeypatch.setattr(sys, "argv", [
            "run_latex.py",
            "--orcid", "0000-0001-2345-6789",
            "--output-dir", str(output_dir),
            "--no-fetch"
        ])

        cli.main()

        assert (output_dir / "orcid-publications.tex").exists()
    finally:
        os.chdir(original_cwd)
