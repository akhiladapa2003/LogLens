# Debugging audit report

Audit date: 2026-11-13. Overall verdict: **PASS WITH LIMITATIONS**. A confirmed SQLite setup failure defect was fixed and regression-tested. The full suite and fresh benchmark pass. Latest rendered pages and manual A/B/A upload sequence are NOT VERIFIED.

## Inspected

app.py; parser.py; validation.py; pipeline.py; database.py; analytics.py; cli.py; generator.py; tests/test_pipeline.py; .streamlit/config.toml; requirements.txt; sample inputs and expected labels; output CSVs; current and historical audit documentation; benchmark artifacts and database schema.

## Findings

| Classification | Finding and cause | Resolution |
|---|---|---|
| FIXED | run_pipeline() configured WAL/synchronous and inserted the run before its try/finally. An injected journal setup error escaped with an open connection and no recorded result. | Moved run registration and setup inside the protected boundary. Post-registration failure records FAILED and reason; finally closes SQLite. A regression reproduced the old failure and passes after fix. |
| FIXED | database.connect() schema-init exceptions must close the opened connection. | Existing close-on-error behavior is now directly regression-tested. |
| PASS | JSON/JSONL user fields cannot overwrite trusted source line, parse error, or raw metadata. | Metadata assigned after parsed source fields; tests retained. |
| PASS | CSV overflow cells could otherwise be silently lost. | Extra cells become malformed quarantine records with physical line; test retained. |
| PASS | Numeric event ID zero could be treated as missing via truthiness. | Zero ID is retained as string; test retained. |
| PASS | Required fields, timestamp/timezone, severity, latency, duplicate conflict, and drift behavior. | Covered by unit/integration tests; no additional rule changes. |
| PASS | Batch rollback and recovery. | Trigger-injected tests prove failed batch rollback and safe retry. |
| PASS | Analytics and CLI export connection close behavior. | contextlib.closing in analytics.summary() and CLI export; source inspected. |
| PARTIAL | Dashboard visual and manual interaction verification. | Current Streamlit process started, but Computer Use was stopped before navigating from stale port 8507 to the isolated latest app. |
| PARTIAL | Performance generalization. | One fresh isolated benchmark; not a statistical or multi-host capacity result. |

## Test and data evidence

Full suite: **21 passed, 0 failed, 0 skipped**. Syntax compilation succeeded for app, pipeline, parsing, validation, database, analytics, CLI, generator and tests. pip check found no broken requirements. Static source/config scan found no hardcoded workstation path or credential.

Final clean benchmark: seed 42; 100002 input; 95291 accepted, 4710 invalid, 1 duplicate; 126.148578 seconds, 792.73 input rows/second. Same-file rerun accepted 0 and reconciled 100002 = 0 + 4710 + 95292. Database integrity_check was ok; foreign_key_check had zero violations. Evidence: reports/final_submission_clean_benchmark_20261113.json.

## Database and pipeline review

SQLite has five tables: pipeline_runs, processed_files, processed_logs, rejected_records and schema_observations. Primary/unique keys, foreign keys, latency constraint, and query indexes are declared. Row IDs and fingerprint uniqueness prevent duplicate writes. Each accepted/invalid/duplicate source row is accounted. Each write batch is transactional; previously committed batches remain recoverable.

No schema or data-validation change was made. The setup failure change addresses cleanup and failure recording only.

## Dashboard and CLI

Source inspection confirms Overview, Run Pipeline and Data Quality pages, file type restrictions, original upload.name display, session hash guard, run history, rejection search/category filter, CSV/JSON download buttons, and schema observations. Current server startup logged successfully at 127.0.0.1:8516. These controls were not tested in the browser during this audit. The requested A/B/A result is therefore NOT VERIFIED.

CLI failed runs use a non-zero exit code, covered by test_cli_failed_pipeline_returns_nonzero_and_prints_failure. Setup failure after run registration returns a FAILED result with a reason.

## Remaining risks

- Latest visual layout, A/B/A rerun guard and browser downloads/filters are not verified; no current screenshots were saved.
- Dashboard supports one file at a time; CLI is preferred for large data.
- Text parser supports two patterns; schema hash is not a full contract registry.
- SQLite is local; performance depends on host and disk.
- Fingerprints can classify identical legitimate events as duplicates when source IDs are absent.
- Historical databases were preserved; the final audit only checked integrity on its fresh benchmark DB.


## Corrective release verification addendum — 2026-11-13

This section supersedes earlier test/UI status above where it conflicts. Root and packaged discovery are now configured independently (`pytest.ini` uses `testpaths = tests`). Root suite: **43 passed**; packaged suite: **pending final synchronized package run**. Rejection regex errors now produce a user-facing message. All app and CLI CSV exports use spreadsheet formula neutralization; JSON and SQLite source values remain unchanged. Streamlit defaults to loopback.

Read-only integrity audit across the six retained DBs: all integrity checks `ok`; zero FK violations, accepted duplicate IDs/fingerprints, or completed-run reconciliation mismatches. A new 100,002-row run and same-input rerun reconciled; first run accepted 95,291, rejected 4,710 and duplicated 1; rerun accepted 0, rejected 4,710 and duplicated 95,292. See `reports/release_benchmark_20261113.json`.

Browser inspection rendered Overview, Run Pipeline and Data Quality; light/dark background styles were observed, category filtering and malformed regex messaging worked, and CSV/JSON buttons were clicked. Actual file upload, filename preservation from upload, A/B/A UI guard, download contents and screenshots remain NOT VERIFIED. No auth exists; network/public deployment is not ready. See `FINAL_RELEASE_READINESS_REPORT.md`.

## Final independent quality review addendum — 2026-11-13

Latest root and packaged test runs each passed **52 tests**. All three Streamlit pages rendered in an isolated browser and light/dark backgrounds were checked; desktop overflow was absent. The native file picker, downloaded bytes, console and narrow viewport were not verified. The upload helper was regression tested for A/B/A. New features are limited to UI upload orchestration, opt-in privacy masking, explicit dry-run-first retention, and empty-export headers; pipeline schema and business validation were preserved. Six existing DBs were read-only and clean. Fresh 100,002-row benchmark reconciled on first run and rerun; no additional rows accepted on rerun. See `FINAL_INDEPENDENT_AUDIT_REPORT.md` and `FINAL_TEST_EVIDENCE.md`. Score 92/100; READY WITH LIMITATIONS.
