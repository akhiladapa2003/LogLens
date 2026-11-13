import json
import sqlite3
import sys

import pytest

import database
import pipeline
import cli
from analytics import summary
from database import connect
from generator import generate
from parser import parse_file
from pipeline import run_pipeline
from validation import canonicalize, normalize_timestamp, schema_version


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def event(event_id="e1", **overrides):
    row = {"event_id": event_id, "timestamp": "2026-01-01T00:00:00Z", "level": "INFO", "service": "api", "message": "ok"}
    return row | overrides


def jsonl(rows):
    return "\n".join(json.dumps(row) for row in rows)


def test_json_object_array_jsonl_csv_and_both_text_patterns(tmp_path):
    assert parse_file(write(tmp_path, "object.json", json.dumps(event())))[0]["event_id"] == "e1"
    assert parse_file(write(tmp_path, "array.json", json.dumps([event(), event("e2")])))[1]["event_id"] == "e2"
    assert parse_file(write(tmp_path, "lines.jsonl", jsonl([event()])))[0]["event_id"] == "e1"
    assert parse_file(write(tmp_path, "rows.csv", "timestamp,level,service,message\n2026-01-01T00:00:00Z,INFO,api,ok\n"))[0]["service"] == "api"
    text_a = parse_file(write(tmp_path, "a.txt", "2026-11-12 10:30:00 ERROR payment Payment failed latency_ms=450"))[0]
    text_b = parse_file(write(tmp_path, "b.log", "[2026-11-12T10:31:00Z] INFO auth Logged in duration=120ms"))[0]
    assert text_a["latency_ms"] == "450" and text_b["duration"] == "120ms"


def test_csv_extra_cells_are_quarantined_with_physical_source_line(tmp_path):
    source = write(tmp_path, "extra.csv", "timestamp,level,service,message\n\n2026-01-01T00:00:00Z,INFO,api,ok,extra\n")
    records = parse_file(source)
    assert records[0]["_source_line"] == 3
    result = run_pipeline(source, tmp_path / "db.sqlite")
    assert (result["input_count"], result["accepted_count"], result["rejected_count"]) == (1, 0, 1)
    db = connect(tmp_path / "db.sqlite")
    rejected = db.execute("SELECT source_line,category,rejection_code,rejection_reason FROM rejected_records").fetchone()
    db.close()
    assert tuple(rejected) == (3, "MALFORMED", "MALFORMED_RECORD", "CSV row has more fields than its header")


@pytest.mark.parametrize("suffix", ["jsonl", "json"])
def test_json_cannot_override_parser_metadata(tmp_path, suffix):
    row = event() | {"_source_line": 900, "_parse_error": "forged", "_raw": "forged"}
    source = write(tmp_path, f"reserved.{suffix}", json.dumps(row) + ("\n" if suffix == "jsonl" else ""))
    parsed = parse_file(source)[0]
    assert parsed["_source_line"] == 1 and parsed["_parse_error"] is None
    assert parsed["_raw"] != "forged"
    result = run_pipeline(source, tmp_path / f"{suffix}.sqlite")
    assert result["accepted_count"] == 1 and result["reconciliation_ok"]
    db = connect(tmp_path / f"{suffix}.sqlite")
    saved = db.execute("SELECT source_line,raw_payload FROM processed_logs").fetchone()
    db.close()
    assert saved[0] == 1 and "forged" in saved[1]


def test_generator_writes_deterministic_expected_labels_separately(tmp_path):
    first=generate(tmp_path/"first.jsonl",count=12,seed=7)
    second=generate(tmp_path/"second.jsonl",count=12,seed=7)
    labels=json.loads(first.with_name("first_expected.json").read_text(encoding="utf-8"))
    assert first.read_bytes()==second.read_bytes()
    assert labels["input_count"]==14 and labels["counts"]=={"INVALID":1,"ACCEPTED":11,"DUPLICATE":1,"MALFORMED":1}
    assert "expected_category" not in first.read_text(encoding="utf-8")


def test_empty_file_and_malformed_record_are_visible(tmp_path):
    empty = run_pipeline(write(tmp_path, "empty.jsonl", ""), tmp_path / "db.sqlite")
    assert empty["status"] == "FAILED" and empty["failure_reason"] == "Input contains no records"
    malformed = run_pipeline(write(tmp_path, "bad.jsonl", "{broken}\n"), tmp_path / "bad.sqlite")
    assert (malformed["input_count"], malformed["rejected_count"], malformed["reconciliation_ok"]) == (1, 1, True)


def test_missing_null_and_incompatible_required_fields_are_quarantined(tmp_path):
    rows = [event() | {"message": None}, {"timestamp": "2026-01-01T00:00:00Z", "level": "INFO", "service": "api"}]
    result = run_pipeline(write(tmp_path, "missing.jsonl", jsonl(rows)), tmp_path / "db.sqlite")
    assert result["rejected_count"] == 2 and result["reconciliation_ok"]
    db = connect(tmp_path / "db.sqlite")
    reasons = {row[0] for row in db.execute("SELECT rejection_code FROM rejected_records")}
    observations = {(row[0], row[1]) for row in db.execute("SELECT field_name,observation FROM schema_observations")}
    db.close()
    assert reasons == {"MISSING_REQUIRED_FIELD"}
    assert ("message", "INCOMPATIBLE_MISSING_REQUIRED_FIELD") in observations


def test_incorrect_required_field_types_are_rejected():
    for changes, expected in [({"service": 7}, "service_name"), ({"message": {"text":"bad"}}, "message"), ({"timestamp": 1}, "timestamp")]:
        normalized, category, code, reason = canonicalize(event(**changes), "x.json", "r", "now")
        assert normalized is None and category == "VALIDATION" and code == "INVALID_FIELD_TYPE"
        assert expected in reason


def test_duplicate_id_conflict_and_duplicate_fingerprint_are_distinguished(tmp_path):
    rows = [event("same"), event("same", message="changed"), event("different")]
    result = run_pipeline(write(tmp_path, "dupes.jsonl", jsonl(rows)), tmp_path / "db.sqlite")
    assert (result["accepted_count"], result["duplicate_count"]) == (1, 2)
    db = connect(tmp_path / "db.sqlite")
    codes = [row[0] for row in db.execute("SELECT rejection_code FROM rejected_records ORDER BY rejection_id")]
    db.close()
    assert codes == ["CONFLICTING_EVENT_ID", "DUPLICATE_FINGERPRINT"]


def test_timestamp_timezone_severity_aliases_and_latency_boundaries():
    base = event(timestamp="2026-11-12T12:00:00+02:00", level="wArN", latency_ms=0)
    rec, _, _, _ = canonicalize(base, "x.json", "r", "now")
    assert rec["event_timestamp"] == "2026-11-12T10:00:00.000000Z"
    assert rec["severity"] == "WARNING" and rec["latency_ms"] == 0
    fatal, *_ = canonicalize(event(level="fatal"), "x", "r", "now")
    assert fatal["severity"] == "CRITICAL"
    assert normalize_timestamp("2026-01-01T00:00:00").endswith("Z")
    zero_id, *_ = canonicalize(event(event_id=0), "x", "r", "now")
    assert zero_id["event_id"] == "0"
    for changes, code in [
        ({"timestamp": "not-time"}, "INVALID_TIMESTAMP"),
        ({"level": "TRACE"}, "UNKNOWN_SEVERITY"),
        ({"latency_ms": -1}, "NEGATIVE_LATENCY"),
        ({"latency_ms": "oops"}, "INVALID_LATENCY"),
    ]:
        normalized, category, actual, _ = canonicalize(event(**changes), "x", "r", "now")
        assert normalized is None and category == "VALIDATION" and actual == code


def test_schema_version_tracks_additive_and_incompatible_fields(tmp_path):
    version, missing, extra = schema_version(event() | {"request_region": "west"})
    assert version.startswith("source-v1-") and missing == [] and extra == ["request_region"]
    result = run_pipeline(write(tmp_path, "drift.jsonl", jsonl([event() | {"new_column": 3}])), tmp_path / "db.sqlite")
    assert result["accepted_count"] == 1
    db = connect(tmp_path / "db.sqlite")
    obs = db.execute("SELECT field_name,observation,schema_version FROM schema_observations").fetchone()
    payload = db.execute("SELECT raw_payload FROM processed_logs").fetchone()[0]
    db.close()
    assert obs[0:2] == ("new_column", "ADDITIVE_UNEXPECTED_FIELD") and obs[2].startswith("source-v1-")
    assert "new_column" in payload


def test_run_id_foreign_key_rejects_invalid_reference(tmp_path):
    db = connect(tmp_path / "db.sqlite")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO processed_logs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", ("e", "f", "t", "i", "INFO", "INFO", "s", "m", None, "f", 1, "missing-run", "{}"))
    db.close()


def test_database_connection_closes_when_schema_initialization_fails(tmp_path, monkeypatch):
    class FailingConnection:
        closed = False

        def executescript(self, _schema):
            raise sqlite3.OperationalError("injected schema initialization failure")

        def close(self):
            self.closed = True

    fake_connection = FailingConnection()
    monkeypatch.setattr(database.sqlite3, "connect", lambda _path: fake_connection)
    with pytest.raises(sqlite3.OperationalError, match="injected schema initialization failure"):
        database.connect(tmp_path / "failed-init.sqlite")
    assert fake_connection.closed


def test_pipeline_setup_failure_records_failed_run_and_closes_connection(tmp_path, monkeypatch):
    source = write(tmp_path, "setup_failure.jsonl", jsonl([event("setup-failure")]))
    real_connect = connect
    opened = {}

    class FailingSetupConnection:
        def __init__(self, wrapped):
            self.wrapped = wrapped
            self.closed = False

        def execute(self, sql, *args):
            if sql == "PRAGMA journal_mode=WAL":
                raise sqlite3.OperationalError("injected journal setup failure")
            return self.wrapped.execute(sql, *args)

        def close(self):
            self.closed = True
            self.wrapped.close()

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

    def tracked_connect(path):
        connection = FailingSetupConnection(real_connect(path))
        opened["connection"] = connection
        return connection

    monkeypatch.setattr(pipeline, "connect", tracked_connect)
    db_path = tmp_path / "setup-failure.sqlite"
    result = run_pipeline(source, db_path)
    assert result["status"] == "FAILED"
    assert result["failure_reason"] == "injected journal setup failure"
    assert opened["connection"].closed
    db = sqlite3.connect(db_path)
    failed_run = db.execute("SELECT status,failure_reason FROM pipeline_runs WHERE run_id=?", (result["run_id"],)).fetchone()
    db.close()
    assert failed_run == ("FAILED", "injected journal setup failure")


def test_late_and_out_of_order_events_use_event_time(tmp_path):
    rows = [event("later", timestamp="2026-02-01T00:00:00Z"), event("earlier", timestamp="2026-01-01T00:00:00Z")]
    result = run_pipeline(write(tmp_path, "late.jsonl", jsonl(rows)), tmp_path / "db.sqlite")
    assert result["accepted_count"] == 2
    db = connect(tmp_path / "db.sqlite")
    times = [row[0] for row in db.execute("SELECT event_timestamp FROM processed_logs ORDER BY event_timestamp")]
    db.close()
    assert times == ["2026-01-01T00:00:00.000000Z", "2026-02-01T00:00:00.000000Z"]
    trend = summary(tmp_path / "db.sqlite")["trends"]
    assert list(trend["hour"]) == ["2026-01-01T00", "2026-02-01T00"] and list(trend["count"]) == [1, 1]


def test_repeated_execution_and_source_reconciliation(tmp_path):
    source = write(tmp_path, "repeat.jsonl", jsonl([event("a"), event("b", level="ERROR"), event("c", timestamp="bad")]))
    first = run_pipeline(source, tmp_path / "db.sqlite")
    second = run_pipeline(source, tmp_path / "db.sqlite")
    assert first["input_count"] == first["accepted_count"] + first["rejected_count"] + first["duplicate_count"] == 3
    assert (first["accepted_count"], first["rejected_count"], first["duplicate_count"]) == (2, 1, 0)
    assert (second["accepted_count"], second["rejected_count"], second["duplicate_count"]) == (0, 1, 2)
    assert second["reconciliation_ok"]


def test_parse_failure_records_failed_run_and_retry_succeeds(tmp_path, monkeypatch):
    source = write(tmp_path, "retry.jsonl", jsonl([event()]))
    real_parser = pipeline.parse_file
    monkeypatch.setattr(pipeline, "parse_file", lambda _: (_ for _ in ()).throw(ValueError("injected parse failure")))
    failed = run_pipeline(source, tmp_path / "db.sqlite")
    assert failed["status"] == "FAILED" and failed["failure_reason"] == "injected parse failure"
    monkeypatch.setattr(pipeline, "parse_file", real_parser)
    recovered = run_pipeline(source, tmp_path / "db.sqlite")
    assert recovered["accepted_count"] == 1 and recovered["status"] == "SUCCESS"


def test_cli_failed_pipeline_returns_nonzero_and_prints_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli", "run", str(tmp_path / "missing.jsonl"), "--db", str(tmp_path / "db.sqlite")])
    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    assert exit_info.value.code == 1
    assert '"status": "FAILED"' in capsys.readouterr().out


def test_database_batch_rollback_then_retry_is_idempotent(tmp_path):
    source = write(tmp_path, "insert_failure.jsonl", jsonl([event("good", message="good"), event("fail", message="fail"), event("last", message="last")]))
    db_path = tmp_path / "db.sqlite"
    db = connect(db_path)
    db.execute("CREATE TRIGGER fail_insert BEFORE INSERT ON processed_logs WHEN NEW.event_id='fail' BEGIN SELECT RAISE(ABORT,'injected insert failure'); END")
    db.commit(); db.close()
    failed = run_pipeline(source, db_path, batch_size=1)
    db = connect(db_path)
    saved = db.execute("SELECT event_id FROM processed_logs").fetchall()
    failed_run = db.execute("SELECT status,accepted_count FROM pipeline_runs WHERE run_id=?", (failed["run_id"],)).fetchone()
    db.execute("DROP TRIGGER fail_insert"); db.commit(); db.close()
    assert failed["status"] == "FAILED" and failed["accepted_count"] == 1
    assert [row[0] for row in saved] == ["good"] and tuple(failed_run) == ("FAILED", 1)
    recovered = run_pipeline(source, db_path, batch_size=1)
    repeated = run_pipeline(source, db_path, batch_size=1)
    assert recovered["accepted_count"] == 2 and recovered["duplicate_count"] == 1
    assert repeated["accepted_count"] == 0 and repeated["duplicate_count"] == 3
    db = connect(db_path)
    assert db.execute("SELECT COUNT(*) FROM processed_logs").fetchone()[0] == 3
    db.close()


def test_single_batch_insert_failure_rolls_back_every_row(tmp_path):
    source = write(tmp_path, "rollback.jsonl", jsonl([event("one", message="one"), event("two", message="two")])); db_path = tmp_path / "db.sqlite"
    db = connect(db_path)
    db.execute("CREATE TRIGGER fail_batch BEFORE INSERT ON processed_logs WHEN NEW.event_id='two' BEGIN SELECT RAISE(ABORT,'fail second insert'); END")
    db.commit(); db.close()
    failed = run_pipeline(source, db_path, batch_size=10)
    db = connect(db_path); count = db.execute("SELECT COUNT(*) FROM processed_logs").fetchone()[0]; db.close()
    assert failed["status"] == "FAILED" and failed["accepted_count"] == 0 and count == 0


def test_analytics_error_rate_latency_percentiles_and_empty_dataset(tmp_path):
    db_path = tmp_path / "db.sqlite"
    empty = summary(db_path)
    assert empty["total_records"] == 0 and empty["error_rate"] == 0 and empty["p95_latency"] is None
    rows = [event(str(i), level="ERROR" if i == 0 else "INFO", latency_ms=i) for i in range(10)]
    result = run_pipeline(write(tmp_path, "analytics.jsonl", jsonl(rows)), db_path)
    metrics = summary(db_path)
    assert result["reconciliation_ok"] and metrics["error_rate"] == 10
    assert metrics["latency_count"] == 10 and metrics["p95_latency"] == pytest.approx(8.55)
