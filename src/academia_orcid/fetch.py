"""ORCID API fetching, caching, and UIN-to-ORCID mapping."""

import json
import logging
import os
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from .config import get_config

try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


class OrcidFetchError(Exception):
    """Raised when ORCID API fetch fails (network error, rate limit, server error).

    This distinguishes transient API failures from legitimate "no data" cases
    (e.g., no ORCID ID on file, --no-fetch with empty cache).
    """


# Module logger
logger = logging.getLogger("academia_orcid.fetch")

# SECURITY: ORCID ID format validation to prevent path traversal
_ORCID_ID_PATTERN = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[0-9X]$")

# Default cache TTL (Time To Live) in seconds: 7 days
# NOTE: This is now configurable via Config, but kept for backward compatibility
DEFAULT_CACHE_TTL = 7 * 24 * 60 * 60

# _cache_metadata key: how many works kept only their summary because the
# /work/{put-code} call failed (429 after retries, 5xx, network). A record with
# any is stale, so the next fetch tries again (audit ORC-09).
MISSING_DETAILS_KEY = "missing_work_details"


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


def missing_work_details(record: dict) -> int:
    """How many works of a cached record lack their details (0 for a complete record)."""
    metadata = record.get("_cache_metadata") or {}
    try:
        return int(metadata.get(MISSING_DETAILS_KEY) or 0)
    except (TypeError, ValueError):
        return 0


def is_cache_fresh(record: dict, ttl_seconds: int = DEFAULT_CACHE_TTL) -> bool:
    """Check if a cached ORCID record is still fresh.

    A record is stale when it has no metadata, is older than the TTL, or was
    cached with some work details missing (``missing_work_details``).

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
    if missing_work_details(record):
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


def add_cache_metadata(record: dict, missing_details: int = 0) -> dict:
    """Add cache metadata to an ORCID record.

    Args:
        record: ORCID record dict
        missing_details: works whose detail fetch failed (recorded only when > 0)

    Returns:
        Record with _cache_metadata added
    """
    record["_cache_metadata"] = {
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "ttl_seconds": DEFAULT_CACHE_TTL,
    }
    if missing_details:
        record["_cache_metadata"][MISSING_DETAILS_KEY] = missing_details
    return record


# en.db's identifiers table (built by coe-data-core): one row per identifier, so a
# person's ORCID iD is their row with Scheme 'orcid' (Rank 1 is the primary one).
IDENTIFIERS_TABLE = "faculty_identifiers"
ORCID_SCHEME = "orcid"


def get_orcid_for_uin(db_path: Path, uin: str) -> str | None:
    """Look up ORCID ID for a UIN from SQLite (en.db).

    Takes the person's lowest-Rank ``orcid`` row (the schema allows several),
    whitespace stripped. Returns None if the UIN has none.

    Raises:
        sqlite3.OperationalError: the database has no ``faculty_identifiers``
            table (en.db older than schema v17) or cannot be read.
    """
    # Read-only: a wrong path fails instead of creating an empty database.
    conn = sqlite3.connect(f"{Path(db_path).resolve().as_uri()}?mode=ro", uri=True)
    try:
        row = conn.execute(
            f"SELECT TRIM(Identifier) FROM {IDENTIFIERS_TABLE} "
            "WHERE UIN = ? AND Scheme = ? AND TRIM(Identifier) != '' "
            "ORDER BY Rank LIMIT 1",
            (uin, ORCID_SCHEME),
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _cache_file(data_dir: Path, orcid_id: str) -> Path:
    return data_dir / get_config().cache_dir_name / f"{orcid_id}.json"


def load_orcid_record(data_dir: Path, orcid_id: str) -> dict | None:
    """Load an ORCID record from the cache (``ORCID_JSON/{orcid}.json``).

    Returns None if the file is missing or unreadable (an unreadable file is
    treated as missing, so it is fetched again).
    """
    # SECURITY: Validate ORCID ID format to prevent path traversal
    if not validate_orcid_id(orcid_id):
        logger.error(f"Invalid ORCID ID format: {orcid_id}")
        return None

    json_file = _cache_file(data_dir, orcid_id)
    if not json_file.exists():
        return None
    try:
        with open(json_file, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(f"Failed to parse JSON from {json_file}: {e}")
        return None


def _write_cache(data_dir: Path, orcid_id: str, record: dict) -> None:
    """Write a cache file whole: to a temporary file, then renamed over the old one,
    so an interrupted write never leaves a truncated file (audit ORC-09)."""
    cache_file = _cache_file(data_dir, orcid_id)
    tmp_file = cache_file.with_name(cache_file.name + ".tmp")
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
        os.replace(tmp_file, cache_file)
        logger.info(f"Cached ORCID record to {cache_file}")
    except OSError as e:
        logger.warning(f"Failed to write cache file for {orcid_id}: {e}")


def fetch_work_details(orcid_id: str, put_code: str, max_retries: int | None = None) -> dict | None:
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
            logger.warning(
                f"Network error fetching work {put_code} (attempt {attempt + 1}/{max_retries}): {type(e).__name__}"
            )
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay *= 2
            else:
                return None

    return None


def fetch_work_details_concurrent(
    orcid_id: str,
    put_codes: list[str],
    max_workers: int | None = None,
    rate_limit_delay: float = 0.3,
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
                executor.submit(fetch_work_details, orcid_id, code): code for code in batch_codes
            }

            for future in as_completed(future_to_code):
                put_code = future_to_code[future]
                try:
                    work_detail = future.result()
                    if work_detail:
                        results[put_code] = work_detail
                except (requests.RequestException, json.JSONDecodeError, KeyError, ValueError) as e:
                    logger.warning(f"Exception fetching work {put_code}: {type(e).__name__}: {e}")

        # Rate limiting between batches
        if batch_end < total:
            time.sleep(rate_limit_delay)

    logger.info(f"Successfully fetched {len(results)}/{total} work details")
    return results


def fetch_orcid_record(orcid_id: str, data_dir: Path) -> dict | None:
    """Fetch ORCID record from API and cache it locally.

    Each work's summary is replaced by its full detail (contributors, citation).
    Works whose detail could not be fetched keep their summary, and their count
    is recorded in ``_cache_metadata`` (``missing_work_details``), which makes the
    cached record stale (audit ORC-09).

    Args:
        orcid_id: ORCID ID to fetch
        data_dir: Base data directory (the cache is ``data_dir/ORCID_JSON/``)

    Returns:
        ORCID record dict, or None for validation failures (invalid ID, missing requests).

    Raises:
        OrcidFetchError: On API errors (non-200 status, network errors, timeouts).
    """
    if not REQUESTS_AVAILABLE:
        logger.warning("requests library not available, cannot fetch ORCID record")
        return None

    # SECURITY: Validate ORCID ID format to prevent injection
    if not validate_orcid_id(orcid_id):
        logger.error(f"Invalid ORCID ID format: {orcid_id}")
        return None

    config = get_config()
    logger.info(f"Fetching ORCID record for {orcid_id} from API...")

    url = f"{config.api_base_url}/{orcid_id}/record"
    headers = {"Accept": "application/json"}

    # Fetch main record — network errors become OrcidFetchError
    try:
        response = requests.get(url, headers=headers, timeout=config.api_timeout)
    except (requests.RequestException, requests.Timeout) as e:
        raise OrcidFetchError(
            f"Network error fetching ORCID record for {orcid_id}: {type(e).__name__}: {e}"
        ) from e

    if response.status_code != 200:
        raise OrcidFetchError(f"ORCID API returned HTTP {response.status_code} for {orcid_id}")

    try:
        record = response.json()
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response for {orcid_id}: {e}")
        return None

    logger.info(f"Successfully fetched main record for {orcid_id}")

    # Fetch detailed work information for each work
    missing = 0
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
                rate_limit_delay=config.rate_limit_delay,
            )

            # Update work summaries with detailed information
            for put_code, work_details in work_details_map.items():
                if put_code in work_group_map:
                    group_idx, summary_idx = work_group_map[put_code]
                    works[group_idx]["work-summary"][summary_idx] = work_details

            missing = len(set(put_codes) - set(work_details_map))
            if missing:
                logger.warning(
                    f"{missing}/{len(put_codes)} work details for {orcid_id} could not be "
                    "fetched (summary kept); the cached record stays stale"
                )

    record = add_cache_metadata(record, missing_details=missing)
    _write_cache(data_dir, orcid_id, record)
    return record


def _fetch_or_fall_back(orcid_id: str, data_dir: Path, cached: dict | None) -> dict | None:
    """Fetch the record; if that fails and a cached one exists, use it with a warning."""
    try:
        return fetch_orcid_record(orcid_id, data_dir)
    except OrcidFetchError as e:
        if not cached:
            raise
        logger.warning(f"ORCID fetch failed for {orcid_id} ({e}); using the cached record")
        return cached


def get_or_fetch_orcid_record(
    data_dir: Path,
    orcid_id: str,
    fetch: bool = True,
    force: bool = False,
    cache_ttl: int | None = None,
) -> dict | None:
    """Get ORCID record from cache, or fetch from API if not found.

    Args:
        data_dir: Base data directory
        orcid_id: ORCID ID to look up
        fetch: If True, fetch from API when not in cache
        force: If True, always fetch from API (ignore cache)
        cache_ttl: Cache TTL in seconds (default: from config, typically 7 days)

    Returns:
        ORCID record dict, or None if not found and fetch disabled.

    A failed refetch (stale or forced) falls back to the cached record, with a
    warning: usable data beats a failed section during an API outage (owner,
    2026-11-12; audit SCH-11, same here).

    Raises:
        OrcidFetchError: Propagated from fetch_orcid_record() on API errors,
            when no cached record exists to fall back to.
    """
    # SECURITY: Validate ORCID ID format (defense in depth - also checked in called functions)
    if not validate_orcid_id(orcid_id):
        logger.error(f"Invalid ORCID ID format: {orcid_id}")
        return None

    # Use config cache_ttl if not specified
    config = get_config()
    if cache_ttl is None:
        cache_ttl = config.cache_ttl

    record = load_orcid_record(data_dir, orcid_id)

    # Force fetch: ignore the cache, unless the fetch fails
    if force and fetch:
        logger.info("Force fetching ORCID record (ignoring cache)...")
        return _fetch_or_fall_back(orcid_id, data_dir, record)

    if record:
        # Check if cache is still fresh
        if is_cache_fresh(record, cache_ttl):
            logger.info(f"Using cached ORCID record for {orcid_id} (fresh)")
            return record
        else:
            logger.info(f"Cached ORCID record for {orcid_id} is stale, refetching...")
            # Cache is stale - fetch new data if allowed
            if fetch:
                return _fetch_or_fall_back(orcid_id, data_dir, record)
            else:
                logger.warning("Using stale cache (fetch disabled)")
                return record

    # Not in cache - try fetching if enabled
    if fetch:
        return fetch_orcid_record(orcid_id, data_dir)

    return None
