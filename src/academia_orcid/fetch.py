"""ORCID API fetching, caching, and UIN-to-ORCID mapping."""

import json
import logging
import re
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from .config import get_config

# Module logger
logger = logging.getLogger("academia_orcid.fetch")

# SECURITY: ORCID ID format validation to prevent path traversal
_ORCID_ID_PATTERN = re.compile(r'^\d{4}-\d{4}-\d{4}-\d{3}[0-9X]$')

# Default cache TTL (Time To Live) in seconds: 7 days
# NOTE: This is now configurable via Config, but kept for backward compatibility
DEFAULT_CACHE_TTL = 7 * 24 * 60 * 60


def validate_orcid_id(orcid_id: str) -> bool:
    """Validate ORCID ID format.

    ORCID IDs must match the pattern: XXXX-XXXX-XXXX-XXXX where X is a digit,
    and the last character can be a digit or 'X'.

    This prevents path traversal attacks via malicious ORCID IDs like '../../../etc/passwd'.

    Args:
        orcid_id: The ORCID ID to validate

    Returns:
        True if valid format, False otherwise
    """
    if not orcid_id or not isinstance(orcid_id, str):
        return False
    return _ORCID_ID_PATTERN.match(orcid_id) is not None


def sanitize_dept(dept: str | None) -> str | None:
    """Sanitize department parameter to prevent path traversal.

    Only allows alphanumeric characters, underscores, and hyphens.
    Rejects any path components like '..' or '/'.

    Args:
        dept: Department code to sanitize

    Returns:
        Sanitized department code, or None if invalid/None
    """
    if not dept:
        return None

    # Only allow alphanumeric, underscore, and hyphen
    if not re.match(r'^[a-zA-Z0-9_-]+$', dept):
        return None

    return dept


def is_cache_fresh(record: dict, ttl_seconds: int = DEFAULT_CACHE_TTL) -> bool:
    """Check if a cached ORCID record is still fresh.

    Args:
        record: ORCID record dict with optional _cache_metadata
        ttl_seconds: Time to live in seconds (default: 7 days)

    Returns:
        True if cache is fresh, False if stale or no metadata
    """
    metadata = record.get("_cache_metadata")
    if not metadata:
        # No metadata means old cache format - consider stale
        return False

    cached_at_str = metadata.get("cached_at")
    if not cached_at_str:
        return False

    try:
        cached_at = datetime.fromisoformat(cached_at_str)
        now = datetime.now(timezone.utc)
        age_seconds = (now - cached_at).total_seconds()
        return age_seconds < ttl_seconds
    except (ValueError, TypeError):
        # Invalid timestamp format - consider stale
        return False


def add_cache_metadata(record: dict) -> dict:
    """Add cache metadata to an ORCID record.

    Args:
        record: ORCID record dict

    Returns:
        Record with _cache_metadata added
    """
    record["_cache_metadata"] = {
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "ttl_seconds": DEFAULT_CACHE_TTL,
    }
    return record


def get_orcid_for_uin(db_path: Path, uin: str) -> str | None:
    """Look up ORCID ID for a UIN from SQLite (shared.db).

    Returns ORCID ID string, or None if not found.
    """
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "SELECT ORCID FROM orcid_mapping WHERE UIN = ?", (uin,)
        )
        row = cur.fetchone()
        if row and row[0]:
            return row[0]
        return None
    finally:
        conn.close()


def load_orcid_record(data_dir: Path, orcid_id: str, dept: str = None) -> dict | None:
    """Load ORCID JSON record from cache."""
    # SECURITY: Validate ORCID ID format to prevent path traversal
    if not validate_orcid_id(orcid_id):
        logger.error(f"Invalid ORCID ID format: {orcid_id}")
        return None

    # SECURITY: Sanitize department parameter
    dept = sanitize_dept(dept)

    config = get_config()
    json_dir = data_dir / config.cache_dir_name

    # Try hierarchical structure first (ORCID_JSON/DEPT/orcid.json)
    if dept:
        json_file = json_dir / dept / f"{orcid_id}.json"
        if json_file.exists():
            try:
                with open(json_file, encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from {json_file}: {e}")
                return None

    # Try flat structure (ORCID_JSON/orcid.json)
    json_file = json_dir / f"{orcid_id}.json"
    if json_file.exists():
        try:
            with open(json_file, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from {json_file}: {e}")
            return None

    # Search all subdirectories
    for subdir in json_dir.iterdir():
        if subdir.is_dir():
            json_file = subdir / f"{orcid_id}.json"
            if json_file.exists():
                try:
                    with open(json_file, encoding="utf-8") as f:
                        return json.load(f)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON from {json_file}: {e}")
                    return None

    return None


def fetch_work_details(orcid_id: str, put_code: str, max_retries: int = None) -> dict | None:
    """Fetch detailed work information from ORCID API."""
    if not REQUESTS_AVAILABLE:
        return None

    # SECURITY: Validate ORCID ID format to prevent injection
    if not validate_orcid_id(orcid_id):
        logger.error(f"Invalid ORCID ID format: {orcid_id}")
        return None

    config = get_config()
    if max_retries is None:
        max_retries = config.max_retries

    url = f"{config.api_base_url}/{orcid_id}/work/{put_code}"
    headers = {"Accept": "application/json"}

    delay = config.rate_limit_backoff
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=config.work_detail_timeout)
            if response.status_code == 200:
                try:
                    return response.json()
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON response for work {put_code}: {e}")
                    return None
            elif response.status_code == 429:  # Rate limited
                time.sleep(delay)
                delay *= 2
            else:
                return None
        except (requests.RequestException, requests.Timeout) as e:
            logger.warning(f"Network error fetching work {put_code} (attempt {attempt + 1}/{max_retries}): {type(e).__name__}")
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay *= 2
            else:
                return None

    return None


def fetch_work_details_concurrent(
    orcid_id: str,
    put_codes: list[str],
    max_workers: int = None,
    rate_limit_delay: float = 0.3
) -> dict[str, dict]:
    """Fetch multiple work details concurrently.

    Args:
        orcid_id: ORCID ID
        put_codes: List of put-codes to fetch
        max_workers: Maximum concurrent requests (default: from config)
        rate_limit_delay: Delay between request batches in seconds

    Returns:
        Dictionary mapping put_code to work detail dict
    """
    if not REQUESTS_AVAILABLE or not put_codes:
        return {}

    config = get_config()
    if max_workers is None:
        max_workers = config.max_concurrent_requests

    results = {}
    total = len(put_codes)

    logger.info(f"Fetching {total} work details with {max_workers} concurrent workers...")

    # Process in batches to respect rate limits
    batch_size = max_workers
    for batch_start in range(0, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch_codes = put_codes[batch_start:batch_end]

        # Fetch batch concurrently
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_code = {
                executor.submit(fetch_work_details, orcid_id, code): code
                for code in batch_codes
            }

            for future in as_completed(future_to_code):
                put_code = future_to_code[future]
                try:
                    work_detail = future.result()
                    if work_detail:
                        results[put_code] = work_detail
                except Exception as e:
                    logger.warning(f"Exception fetching work {put_code}: {type(e).__name__}: {e}")

        # Rate limiting between batches
        if batch_end < total:
            time.sleep(rate_limit_delay)

    logger.info(f"Successfully fetched {len(results)}/{total} work details")
    return results


def fetch_orcid_record(orcid_id: str, data_dir: Path, dept: str = None) -> dict | None:
    """Fetch ORCID record from API and cache it locally.

    Args:
        orcid_id: ORCID ID to fetch
        data_dir: Base data directory
        dept: Optional department for hierarchical storage

    Returns:
        ORCID record dict, or None if fetch failed
    """
    if not REQUESTS_AVAILABLE:
        logger.warning("requests library not available, cannot fetch ORCID record")
        return None

    # SECURITY: Validate ORCID ID format to prevent injection
    if not validate_orcid_id(orcid_id):
        logger.error(f"Invalid ORCID ID format: {orcid_id}")
        return None

    # SECURITY: Sanitize department parameter
    dept = sanitize_dept(dept)

    config = get_config()
    logger.info(f"Fetching ORCID record for {orcid_id} from API...")

    url = f"{config.api_base_url}/{orcid_id}/record"
    headers = {"Accept": "application/json"}

    try:
        response = requests.get(url, headers=headers, timeout=config.api_timeout)
        if response.status_code != 200:
            logger.warning(f"ORCID API returned {response.status_code} for {orcid_id}")
            return None

        try:
            record = response.json()
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response for {orcid_id}: {e}")
            return None

        logger.info(f"Successfully fetched main record for {orcid_id}")

        # Fetch detailed work information for each work
        works = record.get("activities-summary", {}).get("works", {}).get("group", [])
        if works:
            # Collect all put-codes first
            put_codes = []
            work_group_map = {}  # Map put_code to (work_group_index, summary_index)

            for group_idx, work_group in enumerate(works):
                work_summaries = work_group.get("work-summary", [])
                if work_summaries:
                    work_summary = work_summaries[0]
                    put_code = work_summary.get("put-code")
                    if put_code:
                        put_code_str = str(put_code)
                        put_codes.append(put_code_str)
                        work_group_map[put_code_str] = (group_idx, 0)

            # Fetch all work details concurrently
            if put_codes:
                work_details_map = fetch_work_details_concurrent(
                    orcid_id,
                    put_codes,
                    max_workers=config.max_concurrent_requests,
                    rate_limit_delay=config.rate_limit_delay
                )

                # Update work summaries with detailed information
                for put_code, work_details in work_details_map.items():
                    if put_code in work_group_map:
                        group_idx, summary_idx = work_group_map[put_code]
                        works[group_idx]["work-summary"][summary_idx] = work_details

        # Add cache metadata before saving
        record = add_cache_metadata(record)

        # Save to cache
        json_dir = data_dir / config.cache_dir_name
        if dept:
            cache_dir = json_dir / dept
        else:
            cache_dir = json_dir

        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"{orcid_id}.json"

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)

        logger.info(f"Cached ORCID record to {cache_file}")
        return record

    except (requests.RequestException, requests.Timeout) as e:
        logger.warning(f"Network error fetching ORCID record for {orcid_id}: {type(e).__name__}: {e}")
        return None
    except OSError as e:
        logger.warning(f"Failed to write cache file for {orcid_id}: {e}")
        return None


def get_or_fetch_orcid_record(
    data_dir: Path,
    orcid_id: str,
    dept: str = None,
    fetch: bool = True,
    force: bool = False,
    cache_ttl: int = None
) -> dict | None:
    """Get ORCID record from cache, or fetch from API if not found.

    Args:
        data_dir: Base data directory
        orcid_id: ORCID ID to look up
        dept: Optional department code
        fetch: If True, fetch from API when not in cache
        force: If True, always fetch from API (ignore cache)
        cache_ttl: Cache TTL in seconds (default: from config, typically 7 days)

    Returns:
        ORCID record dict, or None if not found/fetch failed
    """
    # SECURITY: Validate ORCID ID format (defense in depth - also checked in called functions)
    if not validate_orcid_id(orcid_id):
        logger.error(f"Invalid ORCID ID format: {orcid_id}")
        return None

    # SECURITY: Sanitize department parameter
    dept = sanitize_dept(dept)

    # Use config cache_ttl if not specified
    config = get_config()
    if cache_ttl is None:
        cache_ttl = config.cache_ttl

    # Force fetch: skip cache entirely
    if force and fetch:
        logger.info("Force fetching ORCID record (ignoring cache)...")
        return fetch_orcid_record(orcid_id, data_dir, dept)

    # Try loading from cache first
    record = load_orcid_record(data_dir, orcid_id, dept)
    if record:
        # Check if cache is still fresh
        if is_cache_fresh(record, cache_ttl):
            logger.info(f"Using cached ORCID record for {orcid_id} (fresh)")
            return record
        else:
            logger.info(f"Cached ORCID record for {orcid_id} is stale (age > {cache_ttl}s), refetching...")
            # Cache is stale - fetch new data if allowed
            if fetch:
                return fetch_orcid_record(orcid_id, data_dir, dept)
            else:
                logger.warning("Using stale cache (fetch disabled)")
                return record

    # Not in cache - try fetching if enabled
    if fetch:
        return fetch_orcid_record(orcid_id, data_dir, dept)

    return None
