# Database Audit Report

**Audit date:** 2026-11-13. All retained databases were opened read-only for checks; no production DB was modified.

## Retained databases

| Database | Integrity | FK violations | Accepted | Duplicate IDs | Duplicate fingerprints | Runs | Completed reconciliation mismatches |
|---|---|---:|---:|---:|---:|---:|---:|
| `benchmark.db` | ok | 0 | 95,291 | 0 | 0 | 1 | 0 |
| `comprehensive_audit_benchmark_20261113.db` | ok | 0 | 95,291 | 0 | 0 | 2 | 0 |
| `final_benchmark_20261113.db` | ok | 0 | 95,291 | 0 | 0 | 2 | 0 |
| `final_submission_benchmark_20261113.db` | ok | 0 | 95,291 | 0 | 0 | 2 | 0 |
| `final_submission_clean_benchmark_20261113.db` | ok | 0 | 95,291 | 0 | 0 | 2 | 0 |
| `loglens.db` | ok | 0 | 119 | 0 | 0 | 6 | 0 |

Checks executed per database: `PRAGMA integrity_check`, `PRAGMA foreign_key_check`, accepted duplicate-group queries on event ID and event fingerprint, and count reconciliation for every nonfailed run (`input_count = accepted_count + rejected_count + duplicate_count`).

## Schema and connection behavior

`database.py` defines five tables: `pipeline_runs`, `processed_files`, `processed_logs`, `rejected_records`, and `schema_observations`. Run/rejection/observation identifiers are primary keys; `processed_logs.event_id` is a primary key and `event_fingerprint` is unique; `(source_file, content_hash)` is unique in `processed_files`; child run IDs reference `pipeline_runs`; latency has a nonnegative check; event-time, service/severity, and rejection run/category indexes support dashboard queries. SQLite foreign keys are enabled per connection. Tests cover initialization cleanup, setup-failure cleanup, FK enforcement, batch rollback, retry, and idempotent reprocessing.

## Dashboard/database consistency observation

The isolated UI database was seeded from the sample file (122 physical rows). Direct read-only SQL returned 115 accepted, 47 ERROR/CRITICAL, 6 invalid and 1 duplicate; the run row contained 122 input and reconciled. The browser displayed matching 122 input, 115 accepted, 6 invalid, 1 duplicate and 40.9% error rate. The browser also displayed average latency 61.9 ms. The main retained `loglens.db` was not modified by this check.

## Fresh release benchmark DB

The fresh release benchmark DB is temporary under `tmp/release_benchmark_fresh.sqlite`, outside the retained six. It returned integrity `ok`, zero FK violations, reconciliation passed on first run and rerun, and zero new accepted records on rerun. Evidence is in `reports/release_benchmark_20261113.json`; benchmark DB is intentionally excluded from the submission archive.

## Limitations

No at-rest encryption, retention enforcement, redaction, user-level authorization, or backup policy is implemented. The app is configured for loopback only; any network exposure requires external authentication, authorization, privacy and filesystem controls.
