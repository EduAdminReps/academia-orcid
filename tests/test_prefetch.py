"""Tests for academia_orcid.prefetch (bulk cache fill)."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from academia_orcid import prefetch as pf
from academia_orcid.fetch import OrcidFetchError

FRESH = {"cached_at": datetime.now(timezone.utc).isoformat(), "ttl_seconds": 604800}
STALE = {"cached_at": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
         "ttl_seconds": 604800}
TTL = 7 * 24 * 60 * 60


def _db(tmp_path, rows):
    """en.db's faculty_identifiers, from (UIN, ORCID) pairs; each person also gets a
    Scholars@TAMU row, which load_mapped_orcids must ignore."""
    path = tmp_path / "en.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE faculty_identifiers (UIN TEXT, Scheme TEXT, Identifier TEXT, Rank INTEGER)"
    )
    conn.executemany("INSERT INTO faculty_identifiers VALUES (?, 'orcid', ?, 1)",
                     [(uin, orcid) for uin, orcid in rows if orcid is not None])
    conn.executemany("INSERT INTO faculty_identifiers VALUES (?, 'scholars_tamu', ?, 1)",
                     [(uin, f"n{uin}") for uin, _ in rows])
    conn.commit()
    conn.close()
    return path


def _cache(data_dir, orcid, metadata):
    json_dir = data_dir / "ORCID_JSON"
    json_dir.mkdir(exist_ok=True)
    record = {"activities-summary": {"works": {"group": []}}, "_cache_metadata": metadata}
    (json_dir / f"{orcid}.json").write_text(json.dumps(record))


class TestLoadMappedOrcids:
    def test_skips_blank_and_dedupes(self, tmp_path):
        db = _db(tmp_path, [
            ("222222222", "0000-0002-0000-0002"),
            ("111111111", " 0000-0001-0000-0001 "),
            ("333333333", ""),
            ("444444444", None),
            ("555555555", "0000-0001-0000-0001"),  # same ORCID as 111111111
        ])
        assert pf.load_mapped_orcids(db) == [
            ("111111111", "0000-0001-0000-0001"),
            ("222222222", "0000-0002-0000-0002"),
        ]

    def test_uin_filter(self, tmp_path):
        db = _db(tmp_path, [
            ("111111111", "0000-0001-0000-0001"),
            ("222222222", "0000-0002-0000-0002"),
        ])
        assert pf.load_mapped_orcids(db, ["222222222"]) == [("222222222", "0000-0002-0000-0002")]


class TestFetchReason:
    def test_reasons(self):
        assert pf.fetch_reason(None, TTL, force=False) == "missing"
        assert pf.fetch_reason({"_cache_metadata": STALE}, TTL, force=False) == "stale"
        assert pf.fetch_reason({}, TTL, force=False) == "stale"  # no metadata
        assert pf.fetch_reason({"_cache_metadata": FRESH}, TTL, force=False) is None
        assert pf.fetch_reason({"_cache_metadata": FRESH}, TTL, force=True) == "forced"

    def test_partial_record_is_fetched_again(self):
        partial = {**FRESH, "missing_work_details": 3}
        assert pf.fetch_reason({"_cache_metadata": partial}, TTL, force=False) == "partial"


class TestPrefetch:
    @pytest.fixture
    def calls(self, monkeypatch):
        calls = []

        def fake_fetch(orcid, data_dir):
            calls.append(orcid)
            if orcid.endswith("9999"):
                raise OrcidFetchError("HTTP 503")
            record = {"activities-summary": {"works": {"group": [{}, {}]}}}
            if orcid.endswith("8888"):  # one work detail failed
                record["_cache_metadata"] = {**FRESH, "missing_work_details": 1}
            return record

        monkeypatch.setattr(pf, "fetch_orcid_record", fake_fetch)
        return calls

    def test_fetches_missing_and_stale_skips_fresh(self, tmp_path, calls):
        _cache(tmp_path, "0000-0001-0000-0001", FRESH)
        _cache(tmp_path, "0000-0002-0000-0002", STALE)
        pairs = [("1", "0000-0001-0000-0001"), ("2", "0000-0002-0000-0002"),
                 ("3", "0000-0003-0000-0003")]
        counts = pf.prefetch(pairs, tmp_path)
        assert calls == ["0000-0002-0000-0002", "0000-0003-0000-0003"]
        assert counts["fetched"] == 2 and counts["fresh"] == 1

    def test_force_fetches_fresh(self, tmp_path, calls):
        _cache(tmp_path, "0000-0001-0000-0001", FRESH)
        counts = pf.prefetch([("1", "0000-0001-0000-0001")], tmp_path, force=True)
        assert calls == ["0000-0001-0000-0001"]
        assert counts["fetched"] == 1

    def test_dry_run_fetches_nothing(self, tmp_path, calls):
        counts = pf.prefetch([("1", "0000-0001-0000-0001")], tmp_path, dry_run=True)
        assert calls == []
        assert counts["would-fetch"] == 1

    def test_failure_is_counted_and_run_continues(self, tmp_path, calls):
        pairs = [("1", "0000-0001-0000-9999"), ("2", "0000-0002-0000-0002")]
        counts = pf.prefetch(pairs, tmp_path)
        assert calls == ["0000-0001-0000-9999", "0000-0002-0000-0002"]
        assert counts["failed"] == 1 and counts["fetched"] == 1

    def test_missing_details_counted_partial(self, tmp_path, calls, caplog):
        pairs = [("1", "0000-0001-0000-8888"), ("2", "0000-0002-0000-0002")]
        counts = pf.prefetch(pairs, tmp_path)
        assert counts["fetched"] == 2 and counts["partial"] == 1
        assert "1 without details" in caplog.text

    def test_invalid_id_is_skipped(self, tmp_path, calls):
        counts = pf.prefetch([("1", "../../etc/passwd")], tmp_path)
        assert calls == []
        assert counts["invalid"] == 1


class TestMain:
    def test_exit_code_reflects_failures(self, tmp_path, monkeypatch):
        db = _db(tmp_path, [("111111111", "0000-0001-0000-9999")])

        def boom(orcid, data_dir):
            raise OrcidFetchError("HTTP 503")

        monkeypatch.setattr(pf, "fetch_orcid_record", boom)
        assert pf.main(["--mapping-db", str(db), "--data-dir", str(tmp_path)]) == 1

    def test_dry_run_exits_zero(self, tmp_path):
        db = _db(tmp_path, [("111111111", "0000-0001-0000-0001")])
        args = ["--mapping-db", str(db), "--data-dir", str(tmp_path), "--dry-run"]
        assert pf.main(args) == 0

    def test_missing_db(self, tmp_path):
        assert pf.main(["--mapping-db", str(tmp_path / "nope.db")]) == 1

    def test_pre_v17_db_exits_1(self, tmp_path, caplog):
        old = tmp_path / "old.db"
        sqlite3.connect(old).close()
        assert pf.main(["--mapping-db", str(old), "--data-dir", str(tmp_path)]) == 1
        assert "schema v17" in caplog.text

    def test_unknown_department_fails(self, tmp_path):
        db = _db(tmp_path, [("111111111", "0000-0001-0000-0001")])
        _census(db, [("202631", "111111111", "MEEN")])
        args = ["--mapping-db", str(db), "--data-dir", str(tmp_path), "--dept", "XXXX", "--dry-run"]
        assert pf.main(args) == 1


def _census(db, rows):
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE faculty_census (Term TEXT, UIN TEXT, Department TEXT)")
    conn.executemany("INSERT INTO faculty_census VALUES (?, ?, ?)", rows)
    conn.commit()
    conn.close()


class TestScope:
    def test_read_uin_file_plain_and_csv(self, tmp_path):
        plain = tmp_path / "uins.txt"
        plain.write_text("# nominees\n111111111\n\n222222222\n")
        assert pf.read_uin_file(plain) == ["111111111", "222222222"]
        table = tmp_path / "uins.csv"
        table.write_text("Name,UIN\nAnn,111111111\nBob, 333333333\n")
        assert pf.read_uin_file(table) == ["111111111", "333333333"]

    def test_department_uins_uses_latest_term(self, tmp_path):
        db = _db(tmp_path, [])
        _census(db, [("202611", "999999999", "MEEN"),
                     ("202631", "111111111", "MEEN"),
                     ("202631", "222222222", "ECEN")])
        assert pf.department_uins(db, ["meen"]) == ["111111111"]
        with pytest.raises(ValueError):
            pf.department_uins(db, ["XXXX"])

    def test_selected_uins_is_a_union_and_none_means_everyone(self, tmp_path):
        db = _db(tmp_path, [])
        _census(db, [("202631", "222222222", "ECEN")])
        f = tmp_path / "uins.txt"
        f.write_text("333333333\n")
        assert pf.selected_uins(db) is None
        assert pf.selected_uins(db, ["111111111"], f, ["ECEN"]) == ["111111111", "222222222", "333333333"]

    def test_empty_scope_selects_nobody(self, tmp_path):
        db = _db(tmp_path, [("111111111", "0000-0001-0000-0001")])
        assert pf.load_mapped_orcids(db, []) == []
        assert pf.load_mapped_orcids(db, None) == [("111111111", "0000-0001-0000-0001")]
