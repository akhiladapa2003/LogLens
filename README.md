# LogLens

Local log analytics and data quality pipeline using Python, Pandas, SQLite, Streamlit and Plotly. The application accepts JSON, JSONL/NDJSON, CSV and two timestamped text formats, normalizes events, quarantines invalid/duplicate rows, stores run history, and presents Overview, Run Pipeline and Data Quality views.

## Local setup

Python 3.11+ (verified here with Python 3.12):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python cli.py init-db
python -m streamlit run app.py
```

Streamlit is configured to bind to `127.0.0.1`. There is no built-in authentication or authorization. Keep it on a trusted local machine. Any network/public deployment needs an authenticated access boundary, authorization, suitable privacy controls, and protection for SQLite files and downloads. Uploaded logs remain local. By default, no redaction, encryption, or automatic retention is applied. An opt-in redaction mode masks common credential fields and email addresses before storage; this is heuristic and should be reviewed for your data. A dry-run-first CLI can prune old completed runs; deletion requires an explicit `--apply`. Protect SQLite files and exports at the OS level.

## Dashboard

The app has a light theme by default and a session-level **Dark mode** switch in the sidebar. Pages: **Overview** (KPIs, severity/service charts, event-time trends, latency summaries and recent runs), **Run Pipeline** (single-file upload, processing result and run history), and **Data Quality** (rejection categories, search/filtering, schema observations, CSV and JSON exports).

Rejection search supports case-insensitive regular expressions. Malformed expressions produce a validation message and suppress the filtered table/exports until the query is corrected. CSV downloads neutralize formula-like text at export time; stored SQLite values and JSON export values remain unchanged. Treat JSON downloads as raw source-derived data.

## CLI

```powershell
python cli.py init-db
python cli.py generate --count 120 --seed 42 --output data/sample/sample.jsonl
python cli.py run data/sample/sample.jsonl --db data/loglens.db --batch-size 1000
python cli.py analytics --db data/loglens.db
python cli.py export processed --db data/loglens.db --output reports/processed.csv
python cli.py export rejected --db data/loglens.db --output reports/rejected.csv
```

Failed pipeline runs return a nonzero exit code. Each input row reconciles to accepted, invalid/rejected or duplicate. Batches are transactional; a retry may recognize previously committed rows as duplicates.

## Tests

Activate `.venv` as above, then run the root suite (discovery is restricted to the root `tests/` directory):

```powershell
python -m pytest -q
```

To run the packaged test copy independently:

```powershell
Set-Location LogLens_Submission
..\.venv\Scripts\python.exe -m pytest -q
```

Historical independent audit run (2026-11-13): **52 passed, 0 failed, 0 skipped** in each suite. This count is superseded by the current 2026-11-14 result below. `python -m pip check` and `python -m compileall -q app.py analytics.py cli.py database.py export_utils.py generator.py parser.py pipeline.py privacy.py retention.py upload_workflow.py validation.py tests` also passed.

## Benchmark evidence

**Latest run (2026-11-14):** deterministic generator seed `20261114`, base count `100000`, producing 100,002 physical input rows, on a fresh temporary SQLite database. The first run accepted 95,291 records, rejected 4,710 invalid/malformed records, and classified 1 duplicate in 123.903352 seconds (807.097 records/second). The identical rerun accepted zero, rejected 4,710, and classified 95,292 duplicates in 5.405216 seconds (18,501.018 records/second). Both runs reconciled and the fresh database passed SQLite integrity and foreign-key checks. Machine-readable evidence: `reports/final_verification_benchmark_20261114.json`.

The previously reported Nov 13 benchmark (seed `20261113`) remains historical evidence and has not been overwritten. These are single-host measurements, not a capacity or memory guarantee; parser input and deduplication keys are materialized in memory.

## Final verification status (2026-11-14)

**93/100 — READY WITH LIMITATIONS for local portfolio use.** The running dashboard, real file-upload A/B/A guard, run history, metrics, rejection filters, all four accepted/rejected CSV/JSON browser downloads and database reconciliation were verified. Browser evidence: `reports/final_audit_screenshots/` and `reports/final_audit_downloads/`. The root suite reports **53 passed, 0 failed, 0 skipped** (14.33s), and the synchronized packaged suite reports **53 passed, 0 failed, 0 skipped** (14.79s). Screenshots and downloaded export bytes are saved in the evidence folders. One UI point is withheld because the 390×844 responsive check predates the accepted-export controls; desktop pages were inspected after that small change, but narrow Data Quality was not rechecked. See the final verification addenda in the audit, gap analysis, test evidence and release readiness reports.

## Optional privacy and retention controls

Set `LOGLENS_REDACT_SENSITIVE=1` before running the CLI or Streamlit to enable heuristic redaction of common credential fields and email addresses in stored source-derived text. It is disabled by default to preserve input fidelity and is not a substitute for reviewing sensitive-data handling.

Retention is explicit and dry-run by default; it does not run automatically:

```powershell
python cli.py prune --older-than-days 90 --db data/loglens.db
python cli.py prune --older-than-days 90 --db data/loglens.db --apply
```

`--apply` permanently deletes matching completed runs and their dependent records in one transaction. Back up the database before applying a retention policy.

## Historical independent audit status (2026-11-13)

The prior audit scored 92/100 and left browser upload and downloaded artifact contents unverified. This is retained as a historical record and is superseded by the 2026-11-14 verification above.


The synchronized submission archive contains 55 curated files, includes screenshots, browser download evidence and the current benchmark JSON, passed ZIP CRC validation, and excludes SQLite databases and Python/test caches. See `LogLens_Submission.zip` (also saved as `LogLens_Submission_Final_20261114.zip`).
