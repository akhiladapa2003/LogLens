"""Pipeline orchestration with atomic batches and safe whole-file retries."""
from __future__ import annotations
import hashlib
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from database import connect
from parser import parse_file
from privacy import redact_record, redact_text, redaction_enabled
from validation import canonicalize, schema_version

log_level = getattr(logging, os.environ.get("LOGLENS_LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(level=log_level, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("loglens")

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")

def run_pipeline(source: str | Path, db_path: str | Path = "data/loglens.db", batch_size: int = 1000) -> dict[str, Any]:
    path = Path(source); run_id = str(uuid.uuid4()); start = time.perf_counter()
    start_time = utcnow(); source_name = path.name
    redact_sensitive = redaction_enabled()
    if redact_sensitive:
        source_name = redact_text(source_name)
    db = connect(db_path)
    count = accepted = invalid = duplicates = 0
    file_registered = False
    run_registered = False
    try:
        db.execute("INSERT INTO pipeline_runs(run_id,start_time,source_file,status) VALUES(?,?,?,'FAILED')", (run_id,start_time,source_name)); db.commit()
        run_registered = True
        db.execute("PRAGMA journal_mode=WAL"); db.execute("PRAGMA synchronous=NORMAL")
        raw_bytes = path.read_bytes(); content_hash = hashlib.sha256(raw_bytes).hexdigest()
        records = parse_file(path); count = len(records); ingest_time = utcnow()
        if not records:
            raise ValueError("Input contains no records")
        db.execute("""INSERT INTO processed_files(source_file,content_hash,run_id,status) VALUES(?,?,?,'PROCESSING')
                      ON CONFLICT(source_file,content_hash) DO UPDATE SET run_id=excluded.run_id,status='PROCESSING'""", (source_name,content_hash,run_id))
        db.commit(); file_registered = True

        known_ids = {r[0]: r[1] for r in db.execute("SELECT event_id,event_fingerprint FROM processed_logs")}
        known_fingerprints = {r[0] for r in db.execute("SELECT event_fingerprint FROM processed_logs")}
        log_rows: list[tuple] = []; reject_rows: list[tuple] = []; observation_rows: list[tuple] = []
        pending = {"accepted": 0, "invalid": 0, "duplicates": 0}
        insert_sql = "INSERT INTO processed_logs(event_id,event_fingerprint,event_timestamp,ingestion_timestamp,severity,raw_severity,service_name,message,latency_ms,source_file,source_line,run_id,raw_payload) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)"
        reject_sql = "INSERT INTO rejected_records(run_id,source_file,source_line,rejection_timestamp,category,rejection_code,rejection_reason,raw_payload) VALUES(?,?,?,?,?,?,?,?)"

        def flush() -> None:
            nonlocal accepted, invalid, duplicates
            if not log_rows and not reject_rows and not observation_rows:
                return
            db.execute("SAVEPOINT batch_write")
            try:
                db.executemany(insert_sql, log_rows)
                db.executemany(reject_sql, reject_rows)
                db.executemany("INSERT INTO schema_observations(run_id,source_file,source_line,field_name,observation,schema_version,observed_at) VALUES(?,?,?,?,?,?,?)", observation_rows)
                db.execute("RELEASE batch_write"); db.commit()
            except Exception:
                db.rollback()
                raise
            accepted += pending["accepted"]; invalid += pending["invalid"]; duplicates += pending["duplicates"]
            pending.update(accepted=0, invalid=0, duplicates=0)
            log_rows.clear(); reject_rows.clear(); observation_rows.clear()

        for parsed_row in records:
            row = redact_record(parsed_row) if redact_sensitive else parsed_row
            version, missing_fields, extra_fields = schema_version(row)
            if not row.get("_parse_error"):
                for field in missing_fields:
                    observation_rows.append((run_id,source_name,row.get("_source_line"),field,"INCOMPATIBLE_MISSING_REQUIRED_FIELD",version,ingest_time))
                for field in extra_fields:
                    observation_rows.append((run_id,source_name,row.get("_source_line"),field,"ADDITIVE_UNEXPECTED_FIELD",version,ingest_time))
            normalized, category, code, reason = canonicalize(row,source_name,run_id,ingest_time)
            if normalized:
                normalized.pop("unexpected_fields")
                eid, fingerprint = normalized["event_id"], normalized["event_fingerprint"]
                if eid in known_ids:
                    pending["duplicates"] += 1
                    conflict = known_ids[eid] != fingerprint
                    reject_rows.append((run_id,source_name,row.get("_source_line"),utcnow(),"DUPLICATE","CONFLICTING_EVENT_ID" if conflict else "DUPLICATE_EVENT_ID","Source event ID already exists with different content" if conflict else "Source event ID already exists",row.get("_raw") or json.dumps(row,default=str)))
                elif fingerprint in known_fingerprints:
                    pending["duplicates"] += 1
                    reject_rows.append((run_id,source_name,row.get("_source_line"),utcnow(),"DUPLICATE","DUPLICATE_FINGERPRINT","Canonical event content already exists",row.get("_raw") or json.dumps(row,default=str)))
                else:
                    known_ids[eid] = fingerprint; known_fingerprints.add(fingerprint)
                    log_rows.append(tuple(normalized[k] for k in ("event_id","event_fingerprint","event_timestamp","ingestion_timestamp","severity","raw_severity","service_name","message","latency_ms","source_file","source_line","run_id","raw_payload")))
                    pending["accepted"] += 1
            else:
                pending["invalid"] += 1
                reject_rows.append((run_id,source_name,row.get("_source_line"),utcnow(),category,code,reason,row.get("_raw") or json.dumps(row,default=str)))
            if len(log_rows) + len(reject_rows) >= max(1,batch_size):
                flush()
        flush()
        duration = time.perf_counter()-start; status = "SUCCESS" if invalid + duplicates == 0 else "PARTIAL_SUCCESS"
        db.execute("UPDATE processed_files SET status=? WHERE source_file=? AND content_hash=?", (status,source_name,content_hash))
        db.execute("UPDATE pipeline_runs SET end_time=?,duration_seconds=?,input_count=?,accepted_count=?,rejected_count=?,duplicate_count=?,status=? WHERE run_id=?", (utcnow(),duration,count,accepted,invalid,duplicates,status,run_id)); db.commit()
        result = {"run_id":run_id,"status":status,"input_count":count,"accepted_count":accepted,"rejected_count":invalid,"duplicate_count":duplicates,"duration_seconds":round(duration,6),"source_file":source_name}
        result["reconciliation_ok"] = count == accepted + invalid + duplicates
        if not result["reconciliation_ok"]:
            raise RuntimeError("Source-to-target reconciliation failed")
        log.info("Run %s: %s",run_id,result); return result
    except Exception as exc:
        db.rollback(); duration=time.perf_counter()-start
        if not run_registered:
            raise
        if file_registered:
            db.execute("UPDATE processed_files SET status='FAILED' WHERE source_file=? AND run_id=?", (source_name,run_id))
        db.execute("UPDATE pipeline_runs SET end_time=?,duration_seconds=?,input_count=?,accepted_count=?,rejected_count=?,duplicate_count=?,status='FAILED',failure_reason=? WHERE run_id=?", (utcnow(),duration,count,accepted,invalid,duplicates,str(exc),run_id)); db.commit()
        log.exception("Pipeline failed for %s", source_name)
        return {"run_id":run_id,"status":"FAILED","input_count":count,"accepted_count":accepted,"rejected_count":invalid,"duplicate_count":duplicates,"duration_seconds":round(duration,6),"source_file":source_name,"failure_reason":str(exc),"reconciliation_ok":False}
    finally:
        db.close()
