"""Tests for CLI input validation."""

from academia_orcid.cli import validate_uin


# ── SECURITY: UIN validation ──────────────────────────────────────────────


def test_validate_uin_valid():
    """Test valid UIN formats."""
    assert validate_uin("123456789") is True
    assert validate_uin("000000000") is True
    assert validate_uin("999999999") is True


def test_validate_uin_invalid_length():
    """Test UINs with invalid length are rejected."""
    assert validate_uin("12345678") is False  # Too short
    assert validate_uin("1234567890") is False  # Too long
    assert validate_uin("123") is False
    assert validate_uin("") is False


def test_validate_uin_non_numeric():
    """Test UINs with non-numeric characters are rejected."""
    assert validate_uin("12345678a") is False
    assert validate_uin("abc123456") is False
    assert validate_uin("123-456-789") is False
    assert validate_uin("123 456 789") is False


def test_validate_uin_path_traversal():
    """Test path traversal attempts are rejected."""
    assert validate_uin("../../../etc") is False
    assert validate_uin("../../passwd") is False


def test_validate_uin_empty():
    """Test empty/None values are rejected."""
    assert validate_uin("") is False
    assert validate_uin(None) is False


def test_validate_uin_wrong_type():
    """Test non-string types are rejected."""
    assert validate_uin(123456789) is False
    assert validate_uin(["123456789"]) is False
