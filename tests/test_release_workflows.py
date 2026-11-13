import csv
import json
import sqlite3
import sys
from datetime import datetime, timezone

import pytest

import cli
from analytics import processed_records
from database import connect
from export_utils import dataframe_to_safe_csv
from pipeline import run_pipeline
from privacy import REDACTED, redact_record, redact_text
from retention import prune_old_runs
from upload_workflow import process_uploaded_file


class Uploaded:
    def __init__(self, name: str, content: bytes):
        self.name = name
        self._content = content

    def getvalue(self) -> bytes:
        return self._content


def test_ui_upload_helper_processes_json_csv_and_blocks_a_b_a(tmp_path):
    db_path = tmp_path / "upload.sqlite"
    hashes: set[str] = set()
    a = Uploaded(
        r"C:\fakepath\file_A.json",
        json.dumps({
            "event_id": "upload-a", "timestamp": "2026-11-13T00:00:00Z",
            "level": "INFO", "service": "upload", "message": "A",
        }).encode(),
    )
    b = Uploaded(
        "file_B.csv",
        b"event_id,timestamp,level,service,message\nupload-b,2026-11-13T00:01:00Z,ERROR,upload,B\n",
    )

    first_a, digest_a, skipped_a = process_uploaded_file(a, db_path, hashes)
    result_b, digest_b, skipped_b = process_uploaded_file(b, db_path, hashes)
    repeated_a, repeat_digest, skipped_repeat = process_uploaded_file(a, db_path, hashes)

    assert not skipped_a and not skipped_b and skipped_repeat
    assert digest_a == repeat_digest and digest_a != digest_b
    assert first_a["accepted_count"] == result_b["accepted_count"] == 1
    assert first_a["source_file"] == "file_A.json"
    assert result_b["source_file"] == "file_B.csv"
    assert repeated_a is None
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM processed_logs").fetchone()[0] == 2
        files = dict(db.execute("SELECT source_file,status FROM processed_files"))
        runs = db.execute("SELECT input_count,accepted_count,rejected_count,duplicate_count FROM pipeline_runs").fetchall()
    assert files == {"file_A.json": "SUCCESS", "file_B.csv": "SUCCESS"}
    assert all(row[0] == row[1] + row[2] + row[3] == 1 for row in runs)


def test_upload_helper_keeps_malformed_visible_and_does_not_guard_failed_empty(tmp_path):
    db_path = tmp_path / "upload.sqlite"
    hashes: set[str] = set()
    malformed = Uploaded("bad.jsonl", b"{broken}\n")
    result, digest, skipped = process_uploaded_file(malformed, db_path, hashes)
    assert not skipped and digest in hashes
    assert result["status"] == "PARTIAL_SUCCESS"
    assert (result["input_count"], result["rejected_count"], result["reconciliation_ok"]) == (1, 1, True)

    empty = Uploaded("empty.jsonl", b"")
    failed, empty_hash, skipped = process_uploaded_file(empty, db_path, hashes)
    retry, retry_hash, skipped_retry = process_uploaded_file(empty, db_path, hashes)
    assert failed["status"] == retry["status"] == "FAILED"
    assert not skipped and not skipped_retry and empty_hash == retry_hash not in hashes


def test_redaction_is_off_by_default_and_opt_in_redacts_database_and_raw_payload(tmp_path, monkeypatch):
    source = tmp_path / "sensitive.jsonl"
    original = {
        "event_id": "sensitive-1", "timestamp": "2026-11-13T00:00:00Z",
        "level": "INFO", "service": "audit",
        "message": "user alice@example.com Authorization: Bearer eyJhbGci.secret.signature",
        "password": "top-secret-value", "api_key": "key-secret-value",
    }
    source.write_text(json.dumps(original) + "\n", encoding="utf-8")

    monkeypatch.delenv("LOGLENS_REDACT_SENSITIVE", raising=False)
    raw_db = tmp_path / "raw.sqlite"
    assert run_pipeline(source, raw_db)["accepted_count"] == 1
    with sqlite3.connect(raw_db) as db:
        raw_message = db.execute("SELECT message FROM processed_logs").fetchone()[0]
    assert "alice@example.com" in raw_message

    monkeypatch.setenv("LOGLENS_REDACT_SENSITIVE", "true")
    safe_db = tmp_path / "safe.sqlite"
    result = run_pipeline(source, safe_db)
    assert result["accepted_count"] == 1
    with sqlite3.connect(safe_db) as db:
        message, raw_payload = db.execute("SELECT message,raw_payload FROM processed_logs").fetchone()
    decoded = json.loads(raw_payload)
    assert "alice@example.com" not in message and "eyJhbGci.secret.signature" not in message
    assert decoded["password"] == decoded["api_key"] == REDACTED
    assert "top-secret-value" not in raw_payload and "key-secret-value" not in raw_payload
    assert source.read_text(encoding="utf-8").find("top-secret-value") >= 0


def test_redaction_masks_nested_fields_and_text_patterns():
    original = {
        "headers": {"Authorization": "Bearer token-value"},
        "message": "contact alice@example.com, password='long secret'",
    }
    redacted = redact_record(original)
    assert redacted["headers"]["Authorization"] == REDACTED
    assert "alice@example.com" not in redacted["message"]
    assert "long secret" not in redacted["message"]
    assert "alice@example.com" in original["message"]
    assert "token-value" not in redact_text("Authorization: Bearer token-value")


def test_retention_dry_run_then_apply_preserves_recent_runs_and_integrity(tmp_path):
    db_path = tmp_path / "retention.sqlite"
    old_source = tmp_path / "old.jsonl"
    new_source = tmp_path / "new.jsonl"
    old_source.write_text('{"event_id":"old","timestamp":"2026-01-01T00:00:00Z","level":"INFO","service":"svc","message":"old"}\n', encoding="utf-8")
    new_source.write_text('{"event_id":"new","timestamp":"2026-01-02T00:00:00Z","level":"INFO","service":"svc","message":"new"}\n', encoding="utf-8")
    old = run_pipeline(old_source, db_path)
    recent = run_pipeline(new_source, db_path)
    with connect(db_path) as db:
        db.execute("UPDATE pipeline_runs SET end_time='2026-01-01T00:00:00.000000Z' WHERE run_id=?", (old["run_id"],))
        db.execute("UPDATE pipeline_runs SET end_time='2026-11-12T00:00:00.000000Z' WHERE run_id=?", (recent["run_id"],))

    reference = datetime(2026, 11, 13, tzinfo=timezone.utc)
    preview = prune_old_runs(db_path, 30, now=reference)
    assert preview["dry_run"] and preview["candidate_runs"] == 1
    assert preview["dependent_rows"]["processed_logs"] == 1
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0] == 2

    applied = prune_old_runs(db_path, 30, apply=True, now=reference)
    with sqlite3.connect(db_path) as db:
        assert applied["deleted_runs"] == 1
        assert db.execute("SELECT run_id FROM pipeline_runs").fetchone()[0] == recent["run_id"]
        assert db.execute("SELECT COUNT(*) FROM processed_logs").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM processed_files").fetchone()[0] == 1
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_retention_apply_rolls_back_all_deletes_on_partial_failure(tmp_path):
    db_path = tmp_path / "retention.sqlite"
    source = tmp_path / "old.jsonl"
    source.write_text('{"event_id":"old","timestamp":"2026-01-01T00:00:00Z","level":"INFO","service":"svc","message":"old"}\n', encoding="utf-8")
    result = run_pipeline(source, db_path)
    with connect(db_path) as db:
        db.execute("UPDATE pipeline_runs SET end_time='2026-01-01T00:00:00.000000Z' WHERE run_id=?", (result["run_id"],))
        db.execute("CREATE TRIGGER block_retention BEFORE DELETE ON processed_logs BEGIN SELECT RAISE(ABORT,'injected retention failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match="injected retention failure"):
        prune_old_runs(db_path, 30, apply=True, now=datetime(2026, 11, 13, tzinfo=timezone.utc))
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM processed_logs").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM processed_files").fetchone()[0] == 1
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize(
    ("kind", "expected_columns"),
    [
        ("processed", ["event_id", "event_fingerprint", "event_timestamp"]),
        ("rejected", ["rejection_id", "run_id", "source_file"]),
    ],
)
def test_cli_empty_exports_keep_headers_and_valid_encoding(tmp_path, monkeypatch, capsys, kind, expected_columns):
    db_path = tmp_path / "empty.sqlite"
    output = tmp_path / f"empty_{kind}.csv"
    monkeypatch.setattr(sys, "argv", ["cli", "export", kind, "--db", str(db_path), "--output", str(output)])
    cli.main()
    capsys.readouterr()
    with output.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0][: len(expected_columns)] == expected_columns
    assert len(rows) == 1


def test_cli_rejected_csv_sanitizes_untrusted_filename(tmp_path, monkeypatch, capsys):
    source = tmp_path / "=HYPERLINK.csv"
    source.write_text(
        "event_id,timestamp,level,service,message\n"
        "reject-1,not-a-timestamp,INFO,service,invalid\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "reject.sqlite"
    assert run_pipeline(source, db_path)["rejected_count"] == 1
    output = tmp_path / "rejected.csv"
    monkeypatch.setattr(sys, "argv", ["cli", "export", "rejected", "--db", str(db_path), "--output", str(output)])
    cli.main()
    capsys.readouterr()
    with output.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["source_file"] == "'=HYPERLINK.csv"
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT source_file FROM rejected_records").fetchone()[0] == "=HYPERLINK.csv"


def test_accepted_records_export_has_stable_schema_and_csv_safety(tmp_path):
    source = tmp_path / "accepted.jsonl"
    source.write_text(
        json.dumps({
            "event_id": "accepted-export", "timestamp": "2026-11-13T00:00:00Z",
            "level": "INFO", "service": "export", "message": "=1+1",
        }) + "\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "accepted.sqlite"
    assert run_pipeline(source, db_path)["accepted_count"] == 1

    records = processed_records(db_path)
    csv_text = dataframe_to_safe_csv(records)
    json_text = records.to_json(orient="records", indent=2)

    assert records["event_id"].tolist() == ["accepted-export"]
    assert csv_text.splitlines()[0].startswith("event_id,event_fingerprint,event_timestamp")
    assert "'=1+1" in csv_text
    assert json.loads(json_text)[0]["message"] == "=1+1"
