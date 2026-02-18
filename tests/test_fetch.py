"""Tests for academia_orcid.fetch module."""

import json
import sqlite3
from unittest.mock import Mock, patch

import pytest

from academia_orcid.fetch import (
    fetch_orcid_record,
    fetch_work_details,
    get_orcid_for_uin,
    load_orcid_record,
    sanitize_dept,
    validate_orcid_id,
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


# ── SECURITY: ORCID ID validation ─────────────────────────────────────────


def test_validate_orcid_id_valid():
    """Test valid ORCID ID formats."""
    assert validate_orcid_id("0000-0001-2345-6789") is True
    assert validate_orcid_id("0000-0003-0831-6109") is True
    assert validate_orcid_id("1234-5678-9012-345X") is True  # X is valid checksum


def test_validate_orcid_id_invalid_format():
    """Test invalid ORCID ID formats are rejected."""
    assert validate_orcid_id("0000-0001-2345") is False  # Too short
    assert validate_orcid_id("0000-0001-2345-67890") is False  # Too long
    assert validate_orcid_id("0000-0001-2345-XXXX") is False  # Invalid chars
    assert validate_orcid_id("0000/0001/2345/6789") is False  # Wrong separator
    assert validate_orcid_id("abc-def-ghi-jklm") is False  # Letters


def test_validate_orcid_id_path_traversal():
    """Test path traversal attempts are rejected."""
    assert validate_orcid_id("../../../etc/passwd") is False
    assert validate_orcid_id("../../sensitive") is False
    assert validate_orcid_id("..\\..\\windows\\system32") is False
    assert validate_orcid_id("0000-0001/../../../etc") is False


def test_validate_orcid_id_empty():
    """Test empty/None values are rejected."""
    assert validate_orcid_id("") is False
    assert validate_orcid_id(None) is False


def test_validate_orcid_id_wrong_type():
    """Test non-string types are rejected."""
    assert validate_orcid_id(123) is False
    assert validate_orcid_id(["0000-0001-2345-6789"]) is False


# ── SECURITY: Department sanitization ─────────────────────────────────────


def test_sanitize_dept_valid():
    """Test valid department codes are accepted."""
    assert sanitize_dept("CSCE") == "CSCE"
    assert sanitize_dept("MEEN") == "MEEN"
    assert sanitize_dept("dept-123") == "dept-123"
    assert sanitize_dept("dept_test") == "dept_test"


def test_sanitize_dept_path_traversal():
    """Test path traversal attempts are rejected."""
    assert sanitize_dept("../../../etc") is None
    assert sanitize_dept("../../sensitive") is None
    assert sanitize_dept("..") is None
    assert sanitize_dept(".") is None
    assert sanitize_dept("./subdir") is None


def test_sanitize_dept_special_chars():
    """Test special characters are rejected."""
    assert sanitize_dept("dept/subdir") is None
    assert sanitize_dept("dept\\subdir") is None
    assert sanitize_dept("dept;command") is None
    assert sanitize_dept("dept\x00null") is None
    assert sanitize_dept("dept space") is None


def test_sanitize_dept_empty():
    """Test empty/None values return None."""
    assert sanitize_dept("") is None
    assert sanitize_dept(None) is None


# ── SECURITY: Path traversal protection in load_orcid_record ──────────────


def test_load_orcid_record_rejects_invalid_orcid(tmp_data_dir):
    """Test that load_orcid_record rejects invalid ORCID IDs."""
    record = load_orcid_record(tmp_data_dir, "../../../etc/passwd")
    assert record is None


def test_load_orcid_record_sanitizes_dept(tmp_data_dir):
    """Test that load_orcid_record sanitizes department parameter."""
    # Invalid dept should be sanitized to None, falling back to flat structure
    record = load_orcid_record(tmp_data_dir, "0000-0001-2345-6789", dept="../../../etc")
    # Should still work if file exists in flat structure
    assert record is not None  # From tmp_data_dir fixture


# ── SECURITY: Missing cache directory ─────────────────────────────────────


def test_load_orcid_record_missing_cache_dir(tmp_path):
    """load_orcid_record returns None (not crash) when cache dir is missing."""
    # tmp_path exists but has no ORCID_JSON subdirectory
    record = load_orcid_record(tmp_path, "0000-0001-2345-6789")
    assert record is None


# ── SECURITY: JSON parsing error handling ─────────────────────────────────


def test_load_orcid_record_invalid_json(tmp_data_dir):
    """Test that load_orcid_record handles corrupted JSON files."""
    # Create a file with invalid JSON
    json_dir = tmp_data_dir / "ORCID_JSON"
    json_dir.mkdir(parents=True, exist_ok=True)
    bad_json_file = json_dir / "0000-0001-9999-9999.json"
    bad_json_file.write_text("{invalid json content")

    record = load_orcid_record(tmp_data_dir, "0000-0001-9999-9999")
    assert record is None


def test_load_orcid_record_empty_json(tmp_data_dir):
    """Test that load_orcid_record handles empty JSON files."""
    json_dir = tmp_data_dir / "ORCID_JSON"
    json_dir.mkdir(parents=True, exist_ok=True)
    empty_json_file = json_dir / "0000-0001-8888-8888.json"
    empty_json_file.write_text("")

    record = load_orcid_record(tmp_data_dir, "0000-0001-8888-8888")
    assert record is None


def test_load_orcid_record_truncated_json(tmp_data_dir):
    """Test that load_orcid_record handles truncated JSON files."""
    json_dir = tmp_data_dir / "ORCID_JSON"
    json_dir.mkdir(parents=True, exist_ok=True)
    truncated_file = json_dir / "0000-0001-7777-7777.json"
    truncated_file.write_text('{"person": {"name": ')

    record = load_orcid_record(tmp_data_dir, "0000-0001-7777-7777")
    assert record is None


# ── API MOCKING: fetch_work_details ───────────────────────────────────────


@patch('academia_orcid.fetch.requests')
def test_fetch_work_details_success(mock_requests):
    """Test successful work detail fetch."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"title": {"title": {"value": "Work Title"}}}
    mock_requests.get.return_value = mock_response

    result = fetch_work_details("0000-0001-2345-6789", "12345")

    assert result is not None
    assert result["title"]["title"]["value"] == "Work Title"
    mock_requests.get.assert_called_once()


@patch('academia_orcid.fetch.requests')
def test_fetch_work_details_rate_limit_retry(mock_requests):
    """Test that rate limit (429) triggers retry with exponential backoff."""
    # First call returns 429, second call succeeds
    mock_response_429 = Mock()
    mock_response_429.status_code = 429

    mock_response_200 = Mock()
    mock_response_200.status_code = 200
    mock_response_200.json.return_value = {"title": "Success"}

    mock_requests.get.side_effect = [mock_response_429, mock_response_200]

    result = fetch_work_details("0000-0001-2345-6789", "12345")

    assert result is not None
    assert result["title"] == "Success"
    assert mock_requests.get.call_count == 2  # Retried once


@patch('academia_orcid.fetch.requests')
def test_fetch_work_details_max_retries_exceeded(mock_requests):
    """Test that max retries returns None."""
    mock_response = Mock()
    mock_response.status_code = 429
    mock_requests.get.return_value = mock_response

    result = fetch_work_details("0000-0001-2345-6789", "12345", max_retries=3)

    assert result is None
    assert mock_requests.get.call_count == 3  # All retries exhausted


@patch('academia_orcid.fetch.requests')
def test_fetch_work_details_network_error(mock_requests):
    """Test handling of network errors with retry."""
    import requests
    # First call raises exception, second succeeds
    mock_response_success = Mock()
    mock_response_success.status_code = 200
    mock_response_success.json.return_value = {"title": "Success"}

    mock_requests.get.side_effect = [
        requests.RequestException("Network error"),
        mock_response_success
    ]
    mock_requests.RequestException = requests.RequestException
    mock_requests.Timeout = requests.Timeout

    result = fetch_work_details("0000-0001-2345-6789", "12345")

    assert result is not None
    assert mock_requests.get.call_count == 2


@patch('academia_orcid.fetch.requests')
def test_fetch_work_details_timeout(mock_requests):
    """Test handling of timeout errors."""
    import requests
    mock_requests.Timeout = requests.Timeout
    mock_requests.RequestException = requests.RequestException
    mock_requests.get.side_effect = requests.Timeout("Request timed out")

    result = fetch_work_details("0000-0001-2345-6789", "12345", max_retries=3)

    assert result is None
    assert mock_requests.get.call_count == 3


@patch('academia_orcid.fetch.requests')
def test_fetch_work_details_invalid_json_response(mock_requests):
    """Test handling of invalid JSON in API response."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
    mock_requests.get.return_value = mock_response

    result = fetch_work_details("0000-0001-2345-6789", "12345")

    assert result is None


@patch('academia_orcid.fetch.requests')
def test_fetch_work_details_404_not_found(mock_requests):
    """Test handling of 404 Not Found."""
    mock_response = Mock()
    mock_response.status_code = 404
    mock_requests.get.return_value = mock_response

    result = fetch_work_details("0000-0001-2345-6789", "12345")

    assert result is None


@patch('academia_orcid.fetch.requests')
def test_fetch_work_details_500_server_error(mock_requests):
    """Test handling of 500 Server Error."""
    mock_response = Mock()
    mock_response.status_code = 500
    mock_requests.get.return_value = mock_response

    result = fetch_work_details("0000-0001-2345-6789", "12345")

    assert result is None


# ── API MOCKING: fetch_orcid_record ───────────────────────────────────────


@patch('academia_orcid.fetch.requests')
def test_fetch_orcid_record_success(mock_requests, tmp_path):
    """Test successful ORCID record fetch with caching."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "person": {"name": "Test Person"},
        "activities-summary": {"works": {"group": []}}
    }
    mock_requests.get.return_value = mock_response

    result = fetch_orcid_record("0000-0001-2345-6789", tmp_path)

    assert result is not None
    assert result["person"]["name"] == "Test Person"

    # Verify cache file was created
    cache_file = tmp_path / "ORCID_JSON" / "0000-0001-2345-6789.json"
    assert cache_file.exists()

    # Verify cached content
    with open(cache_file) as f:
        cached_data = json.load(f)
    assert cached_data["person"]["name"] == "Test Person"


@patch('academia_orcid.fetch.requests')
def test_fetch_orcid_record_404(mock_requests, tmp_path):
    """Test handling of 404 Not Found for ORCID record."""
    mock_response = Mock()
    mock_response.status_code = 404
    mock_requests.get.return_value = mock_response

    result = fetch_orcid_record("0000-0009-9999-9999", tmp_path)

    assert result is None


@patch('academia_orcid.fetch.requests')
def test_fetch_orcid_record_invalid_json(mock_requests, tmp_path):
    """Test handling of invalid JSON in ORCID API response."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.side_effect = json.JSONDecodeError("Invalid", "", 0)
    mock_requests.get.return_value = mock_response

    result = fetch_orcid_record("0000-0001-2345-6789", tmp_path)

    assert result is None


@patch('academia_orcid.fetch.requests')
def test_fetch_orcid_record_network_error(mock_requests, tmp_path):
    """Test handling of network errors during fetch."""
    import requests
    mock_requests.RequestException = requests.RequestException
    mock_requests.Timeout = requests.Timeout
    mock_requests.get.side_effect = requests.RequestException("Network down")

    result = fetch_orcid_record("0000-0001-2345-6789", tmp_path)

    assert result is None


@patch('academia_orcid.fetch.requests')
def test_fetch_orcid_record_with_works(mock_requests, tmp_path):
    """Test fetch with works that require detail fetching."""
    # Mock main record fetch
    main_response = Mock()
    main_response.status_code = 200
    main_response.json.return_value = {
        "person": {},
        "activities-summary": {
            "works": {
                "group": [
                    {
                        "work-summary": [
                            {"put-code": 123, "title": {"title": {"value": "Summary"}}}
                        ]
                    }
                ]
            }
        }
    }

    # Mock work detail fetch
    work_detail_response = Mock()
    work_detail_response.status_code = 200
    work_detail_response.json.return_value = {
        "title": {"title": {"value": "Full Detail"}},
        "type": "journal-article"
    }

    mock_requests.get.side_effect = [main_response, work_detail_response]

    result = fetch_orcid_record("0000-0001-2345-6789", tmp_path)

    assert result is not None
    # Work detail should be fetched and merged
    assert mock_requests.get.call_count == 2


@patch('academia_orcid.fetch.requests')
def test_fetch_orcid_record_hierarchical_cache(mock_requests, tmp_path):
    """Test caching with department hierarchy."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"person": {}, "activities-summary": {}}
    mock_requests.get.return_value = mock_response

    result = fetch_orcid_record("0000-0001-2345-6789", tmp_path, dept="CSCE")

    assert result is not None

    # Verify cache in department subdirectory
    cache_file = tmp_path / "ORCID_JSON" / "CSCE" / "0000-0001-2345-6789.json"
    assert cache_file.exists()


# ── API MOCKING: requests unavailable ─────────────────────────────────────


@patch('academia_orcid.fetch.REQUESTS_AVAILABLE', False)
def test_fetch_work_details_no_requests_library():
    """Test that fetch returns None when requests library unavailable."""
    result = fetch_work_details("0000-0001-2345-6789", "12345")
    assert result is None


@patch('academia_orcid.fetch.REQUESTS_AVAILABLE', False)
def test_fetch_orcid_record_no_requests_library(tmp_path, caplog):
    """Test handling when requests library is not available."""
    result = fetch_orcid_record("0000-0001-2345-6789", tmp_path)

    assert result is None

    # Check log messages instead of stderr
    assert "requests library not available" in caplog.text
