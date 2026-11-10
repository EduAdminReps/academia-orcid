"""Bulk cache fill: download every mapped ORCID record into ORCID_JSON/.

The section entry points (run_latex.py, run_json.py) fetch one record on
demand. This command fills the cache ahead of time for every ORCID iD in the
``faculty_identifiers`` table, so report runs can pass ``--no-fetch`` and never wait
on the ORCID API.

A record is downloaded when it is missing, unreadable, or older than the cache
TTL (``cache.ttl_seconds``, 7 days by default); fresh records are skipped.
Records are written one at a time, so an interrupted run can simply be rerun.

Usage (through the justfile, which supplies --mapping-db):
    just prefetch                          # every mapped ORCID iD
    just prefetch --dept MEEN              # current faculty of a department (repeatable)
    just prefetch --uin 123456789          # one person (repeatable)
    just prefetch --uin-file nominees.txt  # one UIN per line, or a CSV with a UIN column
    just prefetch --force                  # refetch even fresh records
    just prefetch --dry-run                # list what would be fetched

Exit code: 0 when every record is cached and fresh, 1 when any fetch failed.
"""

import argparse
import csv
import io
import logging
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

from .config import get_config
from .fetch import (
    IDENTIFIERS_TABLE,
    ORCID_SCHEME,
    OrcidFetchError,
    fetch_orcid_record,
    is_cache_fresh,
    load_orcid_record,
    validate_orcid_id,
)
from .logging_config import setup_logging

logger = logging.getLogger("academia_orcid.prefetch")


def load_mapped_orcids(db_path: Path, uins: list[str] | None = None) -> list[tuple[str, str]]:
    """Return (UIN, ORCID) pairs from ``faculty_identifiers``, one per distinct ORCID.

    Only Scheme 'orcid' rows; a blank ORCID is skipped. ``uins`` restricts the
    result to those UINs. Pairs come back sorted by UIN.
    """
    conn = sqlite3.connect(f"{Path(db_path).resolve().as_uri()}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            f"SELECT UIN, TRIM(Identifier) FROM {IDENTIFIERS_TABLE} "
            "WHERE Scheme = ? AND TRIM(Identifier) != '' ORDER BY UIN",
            (ORCID_SCHEME,),
        ).fetchall()
    finally:
        conn.close()

    # None = everyone mapped; an empty list = nobody (a scope that matched no one).
    wanted = set(uins) if uins is not None else None
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for uin, orcid in rows:
        if wanted is not None and uin not in wanted:
            continue
        if orcid in seen:
            continue
        seen.add(orcid)
        pairs.append((uin, orcid))
    return pairs


def read_uin_file(path: Path) -> list[str]:
    """UINs listed in a file.

    Two formats: one UIN per line (blank lines and ``#`` comments ignored), or a
    CSV whose header has a ``UIN`` column (other columns ignored).
    """
    lines = [
        ln.strip() for ln in Path(path).read_text().splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    if not lines:
        return []
    if "," in lines[0] and "UIN" in lines[0].upper():
        reader = csv.DictReader(io.StringIO("\n".join(lines)))
        column = next((c for c in reader.fieldnames or [] if c.strip().upper() == "UIN"), None)
        if column is None:
            raise ValueError(f"{path}: CSV header has no UIN column")
        return [row[column].strip() for row in reader if (row.get(column) or "").strip()]
    return lines


def department_uins(db_path: Path, departments: list[str]) -> list[str]:
    """UINs of the latest ``faculty_census`` term in the given departments.

    Raises ValueError for a department with nobody in the census (likely a typo).
    """
    wanted = [d.strip().upper() for d in departments]
    conn = sqlite3.connect(f"{Path(db_path).resolve().as_uri()}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT UIN, UPPER(TRIM(Department)) FROM faculty_census "
            "WHERE Term = (SELECT MAX(Term) FROM faculty_census)"
        ).fetchall()
    finally:
        conn.close()
    found = {d: [str(u) for u, dept in rows if dept == d] for d in wanted}
    empty = [d for d, uins in found.items() if not uins]
    if empty:
        raise ValueError(f"no faculty in the latest census for department(s): {', '.join(empty)}")
    return [u for d in wanted for u in found[d]]


def selected_uins(
    db_path: Path,
    uins: list[str] | None = None,
    uin_file: str | Path | None = None,
    departments: list[str] | None = None,
) -> list[str] | None:
    """The UINs a run is limited to (the union of the options), or None for everyone mapped."""
    if not (uins or uin_file or departments):
        return None
    out = list(uins or [])
    if uin_file:
        out += read_uin_file(Path(uin_file))
    if departments:
        out += department_uins(db_path, departments)
    return sorted(set(out))


def fetch_reason(record: dict | None, ttl_seconds: int, force: bool) -> str | None:
    """Why a cached record must be downloaded again, or None if it is fresh."""
    if force:
        return "forced"
    if record is None:
        return "missing"
    if not is_cache_fresh(record, ttl_seconds):
        return "stale"
    return None


def prefetch(
    pairs: list[tuple[str, str]],
    data_dir: Path,
    force: bool = False,
    dry_run: bool = False,
    delay: float = 0.0,
) -> Counter:
    """Fill the cache for each (UIN, ORCID) pair; return outcome counts.

    Outcomes: ``fresh`` (skipped), ``fetched``, ``would-fetch`` (dry run),
    ``failed`` (API error), ``invalid`` (malformed ORCID iD in the mapping).
    """
    ttl = get_config().cache_ttl
    counts: Counter = Counter()
    total = len(pairs)

    for i, (uin, orcid) in enumerate(pairs, start=1):
        tag = f"[{i}/{total}] UIN {uin} ORCID {orcid}"

        if not validate_orcid_id(orcid):
            logger.warning(f"{tag}: invalid ORCID iD in mapping, skipped")
            counts["invalid"] += 1
            continue

        reason = fetch_reason(load_orcid_record(data_dir, orcid), ttl, force)
        if reason is None:
            logger.debug(f"{tag}: fresh, skipped")
            counts["fresh"] += 1
            continue

        if dry_run:
            logger.info(f"{tag}: would fetch ({reason})")
            counts["would-fetch"] += 1
            continue

        try:
            record = fetch_orcid_record(orcid, data_dir)
        except OrcidFetchError as e:
            logger.error(f"{tag}: fetch failed: {e}")
            counts["failed"] += 1
            continue

        if record is None:
            logger.error(f"{tag}: fetch returned no record")
            counts["failed"] += 1
            continue

        n_works = len(record.get("activities-summary", {}).get("works", {}).get("group", []))
        logger.info(f"{tag}: fetched ({reason}), {n_works} works")
        counts["fetched"] += 1

        if delay and i < total:
            time.sleep(delay)

    return counts


def _summary(counts: Counter) -> str:
    order = ["fetched", "would-fetch", "fresh", "failed", "invalid"]
    return ", ".join(f"{counts[k]} {k}" for k in order if counts[k])


def main(argv: list[str] | None = None, default_data_dir: Path | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download every mapped ORCID record into the local cache."
    )
    parser.add_argument("--mapping-db", required=True,
                        help="SQLite database with the faculty_identifiers table (en.db)")
    parser.add_argument("--data-dir", default=str(default_data_dir or "."),
                        help="Base directory holding ORCID_JSON/ (default: repo root)")
    parser.add_argument("--uin", action="append", default=None,
                        help="Only this UIN (repeatable); default: every mapped UIN")
    parser.add_argument("--uin-file", default=None,
                        help="Only the UINs in this file (one per line, or a CSV with a UIN column)")
    parser.add_argument("--dept", action="append", default=None,
                        help="Only current faculty of this department (latest faculty_census term; repeatable)")
    parser.add_argument("--force", action="store_true",
                        help="Download every record, even fresh ones")
    parser.add_argument("--dry-run", action="store_true",
                        help="List what would be downloaded, download nothing")
    parser.add_argument("--delay", type=float, default=0.2,
                        help="Seconds to pause between people (default: 0.2)")
    parser.add_argument("--config", default=None,
                        help="Path to YAML configuration file (optional)")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    args = parser.parse_args(argv)

    setup_logging(level=args.log_level)
    if args.log_level != "DEBUG":
        # The fetch module logs every work batch; keep the per-person line readable.
        logging.getLogger("academia_orcid.fetch").setLevel(logging.WARNING)
    get_config(Path(args.config) if args.config else None)

    db_path = Path(args.mapping_db)
    if not db_path.exists():
        logger.error(f"Mapping database not found: {db_path}")
        return 1

    try:
        wanted = selected_uins(db_path, args.uin, args.uin_file, args.dept)
    except (OSError, ValueError) as e:
        logger.error(str(e))
        return 1
    pairs = load_mapped_orcids(db_path, wanted)
    if wanted is not None:
        logger.info(f"{len(wanted)} UINs selected, {len(pairs)} with an ORCID iD")
    data_dir = Path(args.data_dir)
    logger.info(f"{len(pairs)} mapped ORCID iDs; cache: {data_dir / get_config().cache_dir_name}")

    try:
        counts = prefetch(pairs, data_dir, force=args.force, dry_run=args.dry_run,
                          delay=args.delay)
    except KeyboardInterrupt:
        logger.warning("Interrupted; records already written are kept. Rerun to resume.")
        return 130

    logger.info(f"Done: {_summary(counts) or 'nothing to do'}")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
