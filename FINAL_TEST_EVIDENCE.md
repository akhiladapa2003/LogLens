# Final Test Evidence

**Date:** 2026-11-13. All commands ran from `E:\LogLens` using `.venv\Scripts\python.exe`; test temporary directories were rooted in the project `tmp` folder.

## Automated tests

Root:

```powershell
$env:TEMP='E:\LogLens\tmp'; $env:TMP='E:\LogLens\tmp'
.\.venv\Scripts\python.exe -m pytest -q --basetemp=E:/LogLens/tmp/pytest-root-final2
```

Result: **52 passed in 17.19s**.

Curated submission was synchronized from root, then tested independently:

```powershell
Set-Location E:\LogLens\LogLens_Submission
$env:TEMP='E:\LogLens\tmp'; $env:TMP='E:\LogLens\tmp'
..\.venv\Scripts\python.exe -m pytest -q --basetemp=E:/LogLens/tmp/pytest-package-final
```

Result: **52 passed, 0 failed, 0 skipped**. Regression coverage includes validation, malformed/empty input, null/missing values, invalid timestamp/severity/latency, duplicate/conflicting IDs, schema changes, out-of-order events, rollback/retry, idempotency, connection cleanup, formula-safe exports, A/B/A upload helper, redaction, retention and empty CLI exports.

Additional commands passed:

```powershell
.\.venv\Scripts\python.exe -m compileall -q app.py analytics.py cli.py database.py export_utils.py generator.py parser.py pipeline.py privacy.py retention.py upload_workflow.py validation.py tests
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe cli.py --help
.\.venv\Scripts\python.exe cli.py prune --help
```

`pip check`: no broken requirements. `compileall`: no syntax errors. Streamlit startup succeeded on isolated local port 8522; emitted existing `use_container_width` deprecation warnings.

## Dashboard inspection

An isolated copy and isolated seeded SQLite DB were served locally. Browser inspection confirmed Overview metrics/charts/recent run, Run Pipeline upload/form and history controls, and Data Quality categories/search/schema observations/export controls. Dark mode rendered on all three pages; light mode on Run Pipeline had background `rgb(241, 245, 249)` (dark background `rgb(16, 23, 42)`). That tested desktop view had no horizontal overflow. Rejection search reduced matching rows from 7 to 1. Actual native-file-picker upload and downloaded bytes were not available, so neither is marked browser verified; export controls were observed, while download functions are separately covered by code-level tests. Upload helper A/B/A is covered by the regression suite.

## Database evidence

Read-only checks on `data/benchmark.db`, `data/comprehensive_audit_benchmark_20261113.db`, `data/final_benchmark_20261113.db`, `data/final_submission_benchmark_20261113.db`, `data/final_submission_clean_benchmark_20261113.db`, and `data/loglens.db`: `PRAGMA integrity_check=ok` for all; zero FK violations, completed-run reconciliation mismatches, or duplicate accepted event IDs.

## Fresh large-data benchmark

Seed 20261113, generator base count 100,000, deterministic JSONL, 100,002 physical records, SHA-256 `2a95aac70233377049e7a3190a2657863ec14d0f344fe56ef6052016c771b9d9`. Fresh benchmark DB, then same source rerun:

| Pass | Input | Accepted | Invalid | Duplicate | Wall duration | Throughput | Equation |
|---|---:|---:|---:|---:|---:|---:|---|
| First | 100,002 | 95,291 | 4,710 | 1 | 123.096229 s | 812.39/s | 100,002 = 95,291 + 4,710 + 1 |
| Same input | 100,002 | 0 | 4,710 | 95,292 | 5.681722 s | 17,600.65/s | 100,002 = 0 + 4,710 + 95,292 |

Both reconciled; rerun accepted zero additional rows. Benchmark DB integrity `ok`; zero FK violations. Parser-only `parse_file` diagnostic: 0.410338 s. A separate instrumented fresh DB run reported parse 0.367669 s, canonicalization 1.870688 s, SQLite execute-call 118.975753 s, executemany 1.906122 s, commits 0.067568 s, and unaccounted wall 1.791055 s. SQLite execute timing includes statement calls; cursor fetch iteration is outside the wrapper and contributes to unaccounted wall, so these stages are diagnostic and not a fully additive decomposition. See the two JSON evidence files in `reports/`.

Historical benchmark artifacts were not overwritten.

## Final verification addendum — 2026-11-14 (supersedes prior status)

**Current score: 93/100. Verdict: READY WITH LIMITATIONS for local portfolio use.** Score rubric: data correctness/database integrity 30/30; UI workflows 21/22; tests 20/20; privacy/security 12/15; performance 5/8; documentation/reproducibility 5/5. The seven withheld points reflect no built-in authentication, heuristic opt-in redaction, whole-file in-memory parsing/deduplication and a single-host throughput benchmark. This is not approval for public/network deployment.

### Final interactive checks

The running local Streamlit app was opened in the browser at `http://127.0.0.1:8538`. All three pages were rendered and screenshots saved under `reports/final_audit_screenshots/`. Browser console error/warning collection was empty. Existing 390×844 responsive checks remained available from the preceding visual pass; the three pages had no outer horizontal overflow, with data tables scrolling within their own frame.

A/B/A used the real Streamlit file upload control: `A.json` (2 input, 1 accepted, 1 rejected), `B.csv` (1 accepted), then `A.json` again. The second A was identified as already processed in the session; Run Pipeline was disabled and the DB remained at two runs. Subsequent verification inputs were valid JSONL (1 accepted), empty JSONL (visible FAILED run, zero rows), malformed JSONL (1 rejection), and `=2+2.csv` (1 timestamp rejection). The isolated UI database contains six runs, three accepted records, three invalid/rejected records, one schema observation, no duplicates, no foreign-key violations, `integrity_check=ok`, and zero reconciliation differences. The UI’s metrics showed input 6, accepted 3, rejected 3, duplicates 0, error rate 33.3%.

Accepted CSV and JSON plus rejected CSV and JSON were downloaded through the browser. Read-back inspection found 3 rows per export, preserved normalized accepted columns and source lines, and confirmed the CSV formula-like source filename was neutralized (`'=2+2.csv`) while JSON retained the original value. Export evidence is in `reports/final_audit_downloads/`. Accepted-record CSV/JSON UI buttons were added as a targeted fix; pipeline calculations, database schema and business logic were not changed.

### Current tests and runtime checks

Root suite: **53 passed, 0 failed, 0 skipped** (`14.33s`). A first attempt using the OS temp directory failed two upload helper cases because sandbox temp paths were inaccessible; rerunning with `TEMP` and `TMP` pointed to project `tmp` passed. Packaged suite: **53 passed, 0 failed, 0 skipped (14.79s)** after synchronizing source, tests, docs and evidence. Streamlit was started successfully on localhost. Streamlit 1.67 logs its existing `use_container_width` deprecation warnings; browser console warnings/errors were empty.

### New benchmark (do not conflate with historical runs)

Fresh database, deterministic generator seed `20261114`, base count 100,000, yielding **100,002 input rows** including one repeated event and one malformed JSONL row. First pass: **95,291 accepted, 4,710 invalid/rejected, 1 duplicate**, 123.903352 seconds reported by pipeline (807.097 records/second). `100002 = 95291 + 4710 + 1`; reconciliation passed. Same-file rerun: **0 accepted, 4,710 invalid/rejected, 95,292 duplicates**, 5.405216 seconds (18,501.018 records/second); reconciliation passed. Fresh benchmark database `integrity_check=ok`, no foreign-key violations. Full results: `reports/final_verification_benchmark_20261114.json`. The prior Nov 13 benchmark is historical, retained without overwrite; this new run is not a replacement for or claim about those earlier timings.

### Remaining limitations

No built-in authentication/authorization; stay on trusted localhost unless an external access boundary is configured. Redaction remains opt-in and heuristic; raw source-derived data remains in SQLite/JSON exports when disabled. Input parsing and deduplication materialize data in memory, so the benchmark does not establish capacity for larger files or concurrent use. Streamlit deprecation warnings remain. No public deployment, authentication boundary, memory profile, multi-user load test or formal accessibility audit was performed. One UI point is withheld because the 390×844 responsive pass predates the accepted-export control addition; the final desktop pages were captured afterward, but the final narrow Data Quality page was not rechecked.
