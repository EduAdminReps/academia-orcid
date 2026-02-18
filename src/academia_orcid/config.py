"""Configuration management for academia-orcid.

Loads settings from YAML configuration file with sensible defaults.
Supports environment variable overrides for sensitive settings.
"""

import logging
import os
from pathlib import Path
from typing import Any

# Module logger
logger = logging.getLogger("academia_orcid.config")

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


# Default configuration values
DEFAULT_CONFIG = {
    "api": {
        "base_url": "https://pub.orcid.org/v3.0",
        "timeout": 60,
        "work_detail_timeout": 30,
        "max_retries": 3,
        "rate_limit_delay": 0.3,
        "rate_limit_backoff": 0.5,
        "max_concurrent_requests": 5,  # Max concurrent work detail fetches
    },
    "cache": {
        "ttl_seconds": 7 * 24 * 60 * 60,  # 7 days
        "dir_name": "ORCID_JSON",
    },
    "output": {
        "author_limit": 5,
        "json_indent": 2,
    },
}


class Config:
    """Configuration manager for academia-orcid."""

    def __init__(self, config_file: Path | None = None):
        """Initialize configuration.

        Args:
            config_file: Path to YAML config file (optional)
        """
        self._config = self._load_defaults()

        if config_file and config_file.exists():
            self._load_from_file(config_file)

        # Apply environment variable overrides
        self._apply_env_overrides()

    def _load_defaults(self) -> dict[str, Any]:
        """Load default configuration."""
        import copy
        return copy.deepcopy(DEFAULT_CONFIG)

    def _load_from_file(self, config_file: Path) -> None:
        """Load configuration from YAML file.

        Args:
            config_file: Path to YAML config file
        """
        if not YAML_AVAILABLE:
            logger.warning(f"PyYAML not available, cannot load config from {config_file}")
            return

        try:
            with open(config_file, 'r') as f:
                user_config = yaml.safe_load(f)

            if user_config:
                self._merge_config(user_config)
        except Exception as e:
            logger.warning(f"Failed to load config from {config_file}: {e}")

    def _merge_config(self, user_config: dict) -> None:
        """Merge user configuration with defaults.

        Args:
            user_config: User-provided configuration dict
        """
        for section, values in user_config.items():
            if section in self._config and isinstance(values, dict):
                self._config[section].update(values)
            else:
                self._config[section] = values

        # Validate security-sensitive values after merge
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate security-sensitive configuration values."""
        # api.base_url must be HTTPS
        base_url = self._config.get("api", {}).get("base_url", "")
        if base_url and not base_url.startswith("https://"):
            logger.warning(f"Rejecting non-HTTPS api.base_url: {base_url}")
            self._config["api"]["base_url"] = DEFAULT_CONFIG["api"]["base_url"]

        # cache.dir_name must be a simple name (no path separators or traversal)
        dir_name = self._config.get("cache", {}).get("dir_name", "")
        if dir_name and (
            "/" in dir_name or "\\" in dir_name or ".." in dir_name
        ):
            logger.warning(f"Rejecting unsafe cache.dir_name: {dir_name}")
            self._config["cache"]["dir_name"] = DEFAULT_CONFIG["cache"]["dir_name"]

    def _apply_env_overrides(self) -> None:
        """Apply environment variable overrides.

        Supports:
        - ORCID_API_BASE_URL
        - ORCID_CACHE_TTL
        - ORCID_API_TIMEOUT
        """
        if base_url := os.getenv("ORCID_API_BASE_URL"):
            self._config["api"]["base_url"] = base_url

        if cache_ttl := os.getenv("ORCID_CACHE_TTL"):
            try:
                self._config["cache"]["ttl_seconds"] = int(cache_ttl)
            except ValueError:
                pass

        if timeout := os.getenv("ORCID_API_TIMEOUT"):
            try:
                self._config["api"]["timeout"] = int(timeout)
            except ValueError:
                pass

    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Get configuration value.

        Args:
            section: Configuration section (e.g., 'api', 'cache')
            key: Configuration key within section
            default: Default value if not found

        Returns:
            Configuration value or default
        """
        return self._config.get(section, {}).get(key, default)

    @property
    def api_base_url(self) -> str:
        """Get ORCID API base URL."""
        return self.get("api", "base_url")

    @property
    def api_timeout(self) -> int:
        """Get API request timeout in seconds."""
        return self.get("api", "timeout")

    @property
    def work_detail_timeout(self) -> int:
        """Get work detail request timeout in seconds."""
        return self.get("api", "work_detail_timeout")

    @property
    def max_retries(self) -> int:
        """Get maximum number of API retries."""
        return self.get("api", "max_retries")

    @property
    def rate_limit_delay(self) -> float:
        """Get rate limit delay in seconds."""
        return self.get("api", "rate_limit_delay")

    @property
    def rate_limit_backoff(self) -> float:
        """Get rate limit backoff initial delay in seconds."""
        return self.get("api", "rate_limit_backoff")

    @property
    def max_concurrent_requests(self) -> int:
        """Get maximum number of concurrent API requests."""
        return self.get("api", "max_concurrent_requests")

    @property
    def cache_ttl(self) -> int:
        """Get cache TTL in seconds."""
        return self.get("cache", "ttl_seconds")

    @property
    def cache_dir_name(self) -> str:
        """Get cache directory name."""
        return self.get("cache", "dir_name")

    @property
    def author_limit(self) -> int:
        """Get author display limit."""
        return self.get("output", "author_limit")

    @property
    def json_indent(self) -> int:
        """Get JSON output indentation."""
        return self.get("output", "json_indent")


# Global default config instance
_default_config = None


def get_config(config_file: Path | None = None) -> Config:
    """Get configuration instance.

    Args:
        config_file: Optional path to config file

    Returns:
        Config instance
    """
    global _default_config

    if config_file:
        _default_config = Config(config_file)
        return _default_config

    if _default_config is None:
        # Try to load from default locations
        default_paths = [
            Path.cwd() / ".academia-orcid.yaml",
            Path.home() / ".academia-orcid.yaml",
            Path("/etc/academia-orcid/config.yaml"),
        ]

        for path in default_paths:
            if path.exists():
                _default_config = Config(path)
                break

        if _default_config is None:
            _default_config = Config()

    return _default_config
