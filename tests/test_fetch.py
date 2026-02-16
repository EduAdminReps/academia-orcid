"""Tests for academia_orcid.fetch module."""

import sqlite3

import pytest

from academia_orcid.fetch import (
    get_orcid_for_uin,
    load_orcid_record,
)


# ── get_orcid_for_uin (SQLite) ───────────────────────────────────────────


@pytest.fixture
def tmp_mapping_db(tmp_path):
    """Temp SQLite database with orcid_mapping table."""
    db_path = tmp_path / "shared.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE orcid_mapping (
            UIN TEXT NOT NULL, ORCID TEXT, ScholarsURI TEXT
        )
    """)
    conn.execute(
        "INSERT INTO orcid_mapping VALUES (?, ?, ?)",
        ("123456789", "0000-0001-2345-6789", "https://scholars.library.tamu.edu/test"),
    )
    conn.execute(
        "INSERT INTO orcid_mapping VALUES (?, ?, ?)",
        ("999000000", None, None),
    )
    conn.commit()
    conn.close()
    return db_path


def test_get_orcid_for_uin_found(tmp_mapping_db):
    result = get_orcid_for_uin(tmp_mapping_db, "123456789")
    assert result == "0000-0001-2345-6789"


def test_get_orcid_for_uin_not_found(tmp_mapping_db):
    result = get_orcid_for_uin(tmp_mapping_db, "000000000")
    assert result is None


def test_get_orcid_for_uin_null_orcid(tmp_mapping_db):
    result = get_orcid_for_uin(tmp_mapping_db, "999000000")
    assert result is None


# ── load_orcid_record ──────────────────────────────────────────────────────


def test_load_orcid_record_from_cache(tmp_data_dir):
    record = load_orcid_record(tmp_data_dir, "0000-0001-2345-6789")
    assert record is not None
    assert "person" in record
    assert "activities-summary" in record
