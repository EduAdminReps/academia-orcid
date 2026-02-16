"""ORCID API fetching, caching, and UIN-to-ORCID mapping."""

import json
import re
import sqlite3
import sys
import time
from pathlib import Path

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


# SECURITY: ORCID ID format validation to prevent path traversal
_ORCID_ID_PATTERN = re.compile(r'^\d{4}-\d{4}-\d{4}-\d{3}[0-9X]$')


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
        print(f"Error: Invalid ORCID ID format: {orcid_id}", file=sys.stderr)
        return None

    # SECURITY: Sanitize department parameter
    dept = sanitize_dept(dept)

    json_dir = data_dir / "ORCID_JSON"

    # Try hierarchical structure first (ORCID_JSON/DEPT/orcid.json)
    if dept:
        json_file = json_dir / dept / f"{orcid_id}.json"
        if json_file.exists():
            try:
                with open(json_file, encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                print(f"Error: Failed to parse JSON from {json_file}: {e}", file=sys.stderr)
                return None

    # Try flat structure (ORCID_JSON/orcid.json)
    json_file = json_dir / f"{orcid_id}.json"
    if json_file.exists():
        try:
            with open(json_file, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error: Failed to parse JSON from {json_file}: {e}", file=sys.stderr)
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
                    print(f"Error: Failed to parse JSON from {json_file}: {e}", file=sys.stderr)
                    return None

    return None


def fetch_work_details(orcid_id: str, put_code: str, max_retries: int = 3) -> dict | None:
    """Fetch detailed work information from ORCID API."""
    if not REQUESTS_AVAILABLE:
        return None

    # SECURITY: Validate ORCID ID format to prevent injection
    if not validate_orcid_id(orcid_id):
        print(f"Error: Invalid ORCID ID format: {orcid_id}", file=sys.stderr)
        return None

    url = f"https://pub.orcid.org/v3.0/{orcid_id}/work/{put_code}"
    headers = {"Accept": "application/json"}

    delay = 0.5
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                try:
                    return response.json()
                except json.JSONDecodeError as e:
                    print(f"Error: Failed to parse JSON response for work {put_code}: {e}", file=sys.stderr)
                    return None
            elif response.status_code == 429:  # Rate limited
                time.sleep(delay)
                delay *= 2
            else:
                return None
        except (requests.RequestException, requests.Timeout) as e:
            print(f"Warning: Network error fetching work {put_code} (attempt {attempt + 1}/{max_retries}): {type(e).__name__}", file=sys.stderr)
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay *= 2
            else:
                return None

    return None


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
        print("Warning: requests library not available, cannot fetch ORCID record", file=sys.stderr)
        return None

    # SECURITY: Validate ORCID ID format to prevent injection
    if not validate_orcid_id(orcid_id):
        print(f"Error: Invalid ORCID ID format: {orcid_id}", file=sys.stderr)
        return None

    # SECURITY: Sanitize department parameter
    dept = sanitize_dept(dept)

    print(f"Fetching ORCID record for {orcid_id} from API...", file=sys.stderr)

    url = f"https://pub.orcid.org/v3.0/{orcid_id}/record"
    headers = {"Accept": "application/json"}

    try:
        response = requests.get(url, headers=headers, timeout=60)
        if response.status_code != 200:
            print(f"Warning: ORCID API returned {response.status_code} for {orcid_id}", file=sys.stderr)
            return None

        try:
            record = response.json()
        except json.JSONDecodeError as e:
            print(f"Error: Failed to parse JSON response for {orcid_id}: {e}", file=sys.stderr)
            return None

        print(f"Successfully fetched main record for {orcid_id}", file=sys.stderr)

        # Fetch detailed work information for each work
        works = record.get("activities-summary", {}).get("works", {}).get("group", [])
        if works:
            print(f"Fetching details for {len(works)} works...", file=sys.stderr)
            for work_group in works:
                work_summaries = work_group.get("work-summary", [])
                if work_summaries:
                    work_summary = work_summaries[0]
                    put_code = work_summary.get("put-code")
                    if put_code:
                        work_details = fetch_work_details(orcid_id, str(put_code))
                        if work_details:
                            work_summaries[0] = work_details
                        time.sleep(0.3)  # Rate limiting

        # Save to cache
        json_dir = data_dir / "ORCID_JSON"
        if dept:
            cache_dir = json_dir / dept
        else:
            cache_dir = json_dir

        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"{orcid_id}.json"

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)

        print(f"Cached ORCID record to {cache_file}", file=sys.stderr)
        return record

    except (requests.RequestException, requests.Timeout) as e:
        print(f"Warning: Network error fetching ORCID record for {orcid_id}: {type(e).__name__}: {e}", file=sys.stderr)
        return None
    except OSError as e:
        print(f"Warning: Failed to write cache file for {orcid_id}: {e}", file=sys.stderr)
        return None


def get_or_fetch_orcid_record(
    data_dir: Path,
    orcid_id: str,
    dept: str = None,
    fetch: bool = True,
    force: bool = False
) -> dict | None:
    """Get ORCID record from cache, or fetch from API if not found.

    Args:
        data_dir: Base data directory
        orcid_id: ORCID ID to look up
        dept: Optional department code
        fetch: If True, fetch from API when not in cache
        force: If True, always fetch from API (ignore cache)

    Returns:
        ORCID record dict, or None if not found/fetch failed
    """
    # SECURITY: Validate ORCID ID format (defense in depth - also checked in called functions)
    if not validate_orcid_id(orcid_id):
        print(f"Error: Invalid ORCID ID format: {orcid_id}", file=sys.stderr)
        return None

    # SECURITY: Sanitize department parameter
    dept = sanitize_dept(dept)

    # Force fetch: skip cache entirely
    if force and fetch:
        print("Force fetching ORCID record (ignoring cache)...", file=sys.stderr)
        return fetch_orcid_record(orcid_id, data_dir, dept)

    # Try loading from cache first
    record = load_orcid_record(data_dir, orcid_id, dept)
    if record:
        return record

    # Not in cache - try fetching if enabled
    if fetch:
        return fetch_orcid_record(orcid_id, data_dir, dept)

    return None
