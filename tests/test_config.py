"""Tests for academia_orcid.config module — security validation."""

from academia_orcid.config import Config, DEFAULT_CONFIG


def test_config_rejects_non_https_base_url(tmp_path):
    """Non-HTTPS api.base_url should be rejected and reset to default."""
    config_file = tmp_path / "bad.yaml"
    config_file.write_text("api:\n  base_url: 'http://attacker.com/v3.0'\n")

    cfg = Config(config_file)
    assert cfg.api_base_url == DEFAULT_CONFIG["api"]["base_url"]


def test_config_accepts_https_base_url(tmp_path):
    """HTTPS api.base_url should be accepted."""
    config_file = tmp_path / "good.yaml"
    config_file.write_text("api:\n  base_url: 'https://custom.orcid.org/v3.0'\n")

    cfg = Config(config_file)
    assert cfg.api_base_url == "https://custom.orcid.org/v3.0"


def test_config_rejects_traversal_cache_dir(tmp_path):
    """cache.dir_name with path traversal should be rejected."""
    config_file = tmp_path / "bad.yaml"
    config_file.write_text("cache:\n  dir_name: '../../../tmp/pwned'\n")

    cfg = Config(config_file)
    assert cfg.cache_dir_name == DEFAULT_CONFIG["cache"]["dir_name"]


def test_config_rejects_absolute_cache_dir(tmp_path):
    """cache.dir_name with path separators should be rejected."""
    config_file = tmp_path / "bad.yaml"
    config_file.write_text("cache:\n  dir_name: '/tmp/evil'\n")

    cfg = Config(config_file)
    assert cfg.cache_dir_name == DEFAULT_CONFIG["cache"]["dir_name"]


def test_config_accepts_simple_cache_dir(tmp_path):
    """Simple alphanumeric cache.dir_name should be accepted."""
    config_file = tmp_path / "good.yaml"
    config_file.write_text("cache:\n  dir_name: 'MY_CACHE'\n")

    cfg = Config(config_file)
    assert cfg.cache_dir_name == "MY_CACHE"
