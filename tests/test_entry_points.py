"""The section entry point's contract (run_json.py; academia_orcid.cli's flags,
UIN lookup and record load; audit ORC-12, ORC-13).

The LaTeX and BibTeX entry points went on 2026-11-13: the composer renders the
JSON (tamu-coe-faculty-profiles, formatters/report_latex.py and report_html.py).
"""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import run_json  # noqa: E402
from academia_orcid import cli  # noqa: E402
from academia_orcid.fetch import OrcidFetchError  # noqa: E402

ORCID = "0000-0001-2345-6789"

ENTRY_POINTS = {
    "json": (run_json.main, "orcid-publications.json"),
}


@pytest.fixture(params=sorted(ENTRY_POINTS))
def entry(request):
    return ENTRY_POINTS[request.param]


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "en.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE faculty_identifiers (UIN TEXT, Scheme TEXT, Identifier TEXT, Rank INTEGER)"
    )
    conn.executemany(
        "INSERT INTO faculty_identifiers VALUES (?, ?, ?, ?)",
        [
            ("123456789", "orcid", ORCID, 1),
            ("999999999", "scholars_tamu", "n0000001", 1),
        ],
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def data_dir(tmp_path, sample_record):
    (tmp_path / "ORCID_JSON").mkdir()
    (tmp_path / "ORCID_JSON" / f"{ORCID}.json").write_text(json.dumps(sample_record))
    return tmp_path


def _args(out, data, *extra):
    return ["--output-dir", str(out), "--data-dir", str(data), *extra]


def test_writes_the_section(entry, tmp_path, data_dir):
    main, filename = entry
    main(_args(tmp_path / "out", data_dir, "--orcid", ORCID, "--no-fetch"))
    assert (tmp_path / "out" / filename).exists()


def test_uin_via_en_db(entry, tmp_path, data_dir, db):
    main, filename = entry
    main(
        _args(
            tmp_path / "out", data_dir, "--uin", "123456789", "--mapping-db", str(db), "--no-fetch"
        )
    )
    assert (tmp_path / "out" / filename).exists()


def test_uin_without_orcid_is_no_data(entry, tmp_path, data_dir, db):
    main, _ = entry
    main(
        _args(
            tmp_path / "out", data_dir, "--uin", "999999999", "--mapping-db", str(db), "--no-fetch"
        )
    )
    assert not (tmp_path / "out").exists()


def test_uin_and_orcid_together_are_rejected(entry, tmp_path, data_dir, db):
    main, _ = entry
    with pytest.raises(SystemExit) as exc:
        main(
            _args(
                tmp_path / "out",
                data_dir,
                "--uin",
                "123456789",
                "--orcid",
                ORCID,
                "--mapping-db",
                str(db),
                "--no-fetch",
            )
        )
    assert exc.value.code == 2


def test_neither_uin_nor_orcid_is_rejected(entry, tmp_path, data_dir):
    main, _ = entry
    with pytest.raises(SystemExit) as exc:
        main(_args(tmp_path / "out", data_dir, "--no-fetch"))
    assert exc.value.code == 2


def test_pre_v17_db_exits_1_with_a_message(entry, tmp_path, data_dir, capsys):
    main, _ = entry
    old = tmp_path / "old.db"
    sqlite3.connect(old).close()
    with pytest.raises(SystemExit) as exc:
        main(
            _args(
                tmp_path / "out",
                data_dir,
                "--uin",
                "123456789",
                "--mapping-db",
                str(old),
                "--no-fetch",
            )
        )
    assert exc.value.code == 1
    assert "schema v17" in capsys.readouterr().err


def test_not_cached_under_no_fetch_exits_2(entry, tmp_path):
    main, _ = entry
    with pytest.raises(SystemExit) as exc:
        main(_args(tmp_path / "out", tmp_path, "--orcid", ORCID, "--no-fetch"))
    assert exc.value.code == 2
    assert not (tmp_path / "out").exists()


def test_fetch_error_with_nothing_cached_exits_2(entry, tmp_path, monkeypatch):
    main, _ = entry

    def fail(*_args, **_kwargs):
        raise OrcidFetchError("HTTP 503")

    monkeypatch.setattr(cli, "get_or_fetch_orcid_record", fail)
    with pytest.raises(SystemExit) as exc:
        main(_args(tmp_path / "out", tmp_path, "--orcid", ORCID))
    assert exc.value.code == 2
    assert not (tmp_path / "out").exists()


def test_empty_period_writes_nothing(entry, tmp_path, data_dir):
    main, _ = entry
    main(_args(tmp_path / "out", data_dir, "--orcid", ORCID, "--no-fetch", "--cal_year", "2099"))
    assert not (tmp_path / "out").exists()


def test_json_provenance_carries_the_cache_time(tmp_path, sample_record):
    """run_json stamps the record's fetch time into _meta.provenance."""
    record = dict(sample_record, _cache_metadata={"cached_at": "2026-11-13T00:00:00+00:00"})
    (tmp_path / "ORCID_JSON").mkdir()
    (tmp_path / "ORCID_JSON" / f"{ORCID}.json").write_text(json.dumps(record))
    run_json.main(_args(tmp_path / "out", tmp_path, "--orcid", ORCID, "--no-fetch"))
    meta = json.loads((tmp_path / "out" / "orcid-publications.json").read_text())["_meta"]
    assert meta["provenance"]["fetched_at"] == "2026-11-13T00:00:00+00:00"
    assert meta["provenance"]["curation"] == "author-curated"
