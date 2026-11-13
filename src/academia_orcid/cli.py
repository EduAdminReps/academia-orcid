"""The section entry point's plumbing (run_json.py): the common flags, the UIN →
ORCID lookup and the record load, with one set of exit codes (hand-aligned with
tamu-scholars' cli.py and academia-openalex's section_cli.py):

- 0: done, with or without data (no data writes no file; section contract rule 5)
- 1: bad input (malformed --uin/--orcid, no --mapping-db, an en.db
  without ``faculty_identifiers``)
- 2: argparse errors; the ORCID API failed with nothing cached; under
  ``--no-fetch`` a mapped ORCID with no cache file
"""

import argparse
import logging
import re
import sqlite3
import sys
from pathlib import Path

from academia_orcid.config import get_config
from academia_orcid.fetch import (
    OrcidFetchError,
    get_or_fetch_orcid_record,
    get_orcid_for_uin,
    validate_orcid_id,
)
from academia_orcid.logging_config import setup_logging


def validate_uin(uin: str) -> bool:
    """Validate UIN format.

    UINs must be exactly 9 digits.

    Args:
        uin: The UIN to validate

    Returns:
        True if valid format, False otherwise
    """
    if not uin or not isinstance(uin, str):
        return False
    return bool(re.match(r"^\d{9}$", uin))


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """The flags of the section entry point (run_json.py); it adds --section."""
    who = parser.add_mutually_exclusive_group(required=True)
    who.add_argument("--uin", help="Faculty UIN (looked up in --mapping-db)")
    who.add_argument("--orcid", help="ORCID ID directly (bypasses the UIN→ORCID mapping)")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--data-dir", default=".", help="Base directory containing ORCID_JSON/")
    fetch_group = parser.add_mutually_exclusive_group()
    fetch_group.add_argument(
        "--fetch",
        dest="fetch",
        action="store_true",
        default=True,
        help="Fetch ORCID record from API if not in cache (default)",
    )
    fetch_group.add_argument(
        "--no-fetch",
        dest="fetch",
        action="store_false",
        help="Do not fetch from API, only use cached records",
    )
    fetch_group.add_argument(
        "--force-fetch",
        action="store_true",
        help="Always fetch from API, even if cached record exists (refreshes cache)",
    )
    parser.add_argument(
        "--mapping-db",
        default=None,
        help="Path to SQLite database (en.db) with the faculty_identifiers table (required with --uin)",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to YAML configuration file (optional, defaults to .academia-orcid.yaml)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Optional log file path (logs to stderr if not specified)",
    )


def setup_from_args(args: argparse.Namespace, logger_name: str) -> logging.Logger:
    """Logging and configuration from the common flags; returns the entry point's logger."""
    setup_logging(level=args.log_level, log_file=Path(args.log_file) if args.log_file else None)
    logger = logging.getLogger(logger_name)
    config = get_config(Path(args.config) if args.config else None)
    logger.debug(
        f"Using configuration (cache TTL: {config.cache_ttl}s, API timeout: {config.api_timeout}s)"
    )
    return logger


def resolve_orcid_id(args: argparse.Namespace, logger: logging.Logger) -> str | None:
    """The ORCID iD to report on, from --orcid or from --uin via en.db.

    Returns None when the UIN has no ORCID iD (no data: the caller writes no
    file and exits 0). Exits 1 on a malformed id, a missing --mapping-db, or an
    en.db without the ``faculty_identifiers`` table.
    """
    if args.orcid:
        if not validate_orcid_id(args.orcid):
            logger.error(f"Invalid ORCID ID format: {args.orcid}")
            logger.error("ORCID IDs must match the pattern: XXXX-XXXX-XXXX-XXXX")
            sys.exit(1)
        logger.info(f"Using ORCID ID directly: {args.orcid}")
        return args.orcid

    uin = args.uin
    if not validate_uin(uin):
        logger.error(f"Invalid UIN format: {uin}")
        logger.error("UINs must be exactly 9 digits")
        sys.exit(1)
    if not args.mapping_db:
        logger.error("--mapping-db is required when using --uin")
        sys.exit(1)
    db_path = Path(args.mapping_db)
    if not db_path.exists():
        logger.error(f"Mapping database not found: {db_path}")
        sys.exit(1)

    try:
        orcid_id = get_orcid_for_uin(db_path, uin)
    except sqlite3.Error as e:
        logger.error(
            f"Cannot read faculty_identifiers from {db_path} ({e}); "
            "en.db schema v17 or later is needed (rebuild it with coe-data-core)"
        )
        sys.exit(1)
    if not orcid_id:
        logger.info(f"No ORCID ID on file for UIN {uin}.")
        return None
    logger.info(f"Found ORCID {orcid_id} for UIN {uin}")
    return orcid_id


def load_record(args: argparse.Namespace, orcid_id: str, logger: logging.Logger) -> dict | None:
    """The ORCID record, cached or fetched as the fetch flags say.

    A failed refetch falls back to a cached record (get_or_fetch_orcid_record).
    Exits 2 when the fetch fails with nothing cached, and under --no-fetch when
    the record is not cached (a gap in the cache is not "no data"). Returns None
    only when a fetch returned no record.
    """
    try:
        record = get_or_fetch_orcid_record(
            Path(args.data_dir), orcid_id, fetch=args.fetch, force=args.force_fetch
        )
    except OrcidFetchError as e:
        logger.error(f"ORCID API fetch failed for {orcid_id}: {e}")
        sys.exit(2)
    if not record:
        if not args.fetch:
            logger.error(f"ORCID record for {orcid_id} is not cached; run `just prefetch`.")
            sys.exit(2)
        logger.info(f"No ORCID record for {orcid_id}.")
        return None
    return record
