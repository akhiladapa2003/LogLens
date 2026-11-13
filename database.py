"""SQLite schema and small parameterized query helpers."""
import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS pipeline_runs(run_id TEXT PRIMARY KEY, start_time TEXT NOT NULL, end_time TEXT, duration_seconds REAL, source_file TEXT NOT NULL, input_count INTEGER DEFAULT 0, accepted_count INTEGER DEFAULT 0, rejected_count INTEGER DEFAULT 0, duplicate_count INTEGER DEFAULT 0, status TEXT NOT NULL, failure_reason TEXT);
CREATE TABLE IF NOT EXISTS processed_files(file_id INTEGER PRIMARY KEY, source_file TEXT NOT NULL, content_hash TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id), status TEXT NOT NULL, UNIQUE(source_file,content_hash));
CREATE TABLE IF NOT EXISTS processed_logs(event_id TEXT PRIMARY KEY, event_fingerprint TEXT NOT NULL, event_timestamp TEXT NOT NULL, ingestion_timestamp TEXT NOT NULL, severity TEXT NOT NULL, raw_severity TEXT, service_name TEXT NOT NULL, message TEXT NOT NULL, latency_ms REAL CHECK(latency_ms IS NULL OR latency_ms>=0), source_file TEXT NOT NULL, source_line INTEGER, run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id), raw_payload TEXT NOT NULL, UNIQUE(event_fingerprint));
CREATE TABLE IF NOT EXISTS rejected_records(rejection_id INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id), source_file TEXT NOT NULL, source_line INTEGER, rejection_timestamp TEXT NOT NULL, category TEXT NOT NULL, rejection_code TEXT NOT NULL, rejection_reason TEXT NOT NULL, raw_payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS schema_observations(observation_id INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id), source_file TEXT NOT NULL, source_line INTEGER, field_name TEXT NOT NULL, observation TEXT NOT NULL, schema_version TEXT NOT NULL DEFAULT 'unversioned', observed_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_logs_event_time ON processed_logs(event_timestamp);
CREATE INDEX IF NOT EXISTS idx_logs_service_severity ON processed_logs(service_name,severity);
CREATE INDEX IF NOT EXISTS idx_rejected_run_category ON rejected_records(run_id,category);
"""

def connect(path: str | Path = "data/loglens.db") -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    try:
        db.row_factory = sqlite3.Row
        db.executescript(SCHEMA)
        columns = {row[1] for row in db.execute("PRAGMA table_info(schema_observations)")}
        if "schema_version" not in columns:
            db.execute("ALTER TABLE schema_observations ADD COLUMN schema_version TEXT NOT NULL DEFAULT 'unversioned'")
        return db
    except Exception:
        db.close()
        raise
