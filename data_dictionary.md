# Data dictionary

## Tables and grain

| Table | Grain and key | Main constraints / relationships |
|---|---|---|
| `pipeline_runs` | One row per execution; `run_id` primary key | Records timing, source, reconciliation counts, status and failure reason |
| `processed_files` | One row per unique source filename + SHA-256 content hash | `file_id` primary key; run foreign key; same file content is tracked once and relinked to latest execution |
| `processed_logs` | One accepted unique event; `event_id` primary key | `event_fingerprint` unique; `run_id` references pipeline run; latency nonnegative |
| `rejected_records` | One invalid or duplicate source row; `rejection_id` primary key | `run_id` references pipeline run; category separates invalid from duplicate |
| `schema_observations` | One missing required field or additive field observed per source row | `run_id` references pipeline run; `schema_version` records source-field signature |

## Canonical processed fields

| Field | Type | Nullable | Meaning |
|---|---|---|---|
| event_id | TEXT | No | Source ID (`event_id` or `id`) or deterministic SHA-256 fingerprint |
| event_fingerprint | TEXT | No | Hash of normalized event timestamp, severity, service, message and latency |
| event_timestamp | ISO-8601 UTC TEXT | No | Application event time; naive source timestamps are interpreted as UTC |
| ingestion_timestamp | ISO-8601 UTC TEXT | No | Pipeline receive time, distinct from event time |
| severity | TEXT | No | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| raw_severity | TEXT | Yes | Original source severity string |
| service_name | TEXT | No | Normalized service alias |
| message | TEXT | No | Normalized message alias |
| latency_ms | REAL | Yes | Nonnegative milliseconds |
| source_file | TEXT | No | Source basename |
| source_line | INTEGER | Yes | One-based source line/record position |
| run_id | TEXT | No | Foreign key to pipeline run |
| raw_payload | TEXT | No | Original text or serialized source row |

Source aliases are documented in `validation.py`. Derived fields are `event_fingerprint`, normalized severity/timestamp and analytical aggregates. Rejected records preserve raw payload, filename, source line, run, rejection time, category, code and readable reason. `schema_version` is `source-v1-` plus the first ten SHA-256 hex characters of sorted source fields; schema observations distinguish additive fields from missing required columns. The only reference key is `run_id`, enforced by SQLite; there are no domain reference entities in this model. Analytics are computed from stored records, not generator metadata.

The generator writes a separate `<source_stem>_expected.json` sidecar with source-line expected categories and totals. Expected labels are not included in the input file.
