"""Canonicalization and record validation."""
from __future__ import annotations
import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any

ALIASES = {"event_id": ("event_id", "id"), "timestamp": ("timestamp", "time", "created_at"), "severity": ("level", "severity", "log_level"), "service_name": ("service", "service_name"), "message": ("message", "msg"), "latency_ms": ("latency_ms", "latency", "duration_ms", "duration")}
ALLOWED = set(ALIASES) | {"id", "timestamp", "time", "created_at", "level", "log_level", "service", "msg", "latency", "duration_ms", "duration", "_source_line", "_raw", "_parse_error"}
REQUIRED_ALIASES = {"timestamp": ("timestamp", "time", "created_at"), "severity": ("level", "severity", "log_level"), "service_name": ("service", "service_name"), "message": ("message", "msg")}
SEVERITIES = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

def pick(row: dict[str, Any], key: str) -> Any:
    for alias in ALIASES[key]:
        if alias in row:
            return row[alias]
    return None

def schema_version(row: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    """Return a stable source-field version plus missing and unexpected fields."""
    fields = sorted(k for k in row if isinstance(k, str) and not k.startswith("_") and k not in {"raw_payload"})
    missing = [canonical for canonical, aliases in REQUIRED_ALIASES.items() if not any(alias in row for alias in aliases)]
    unexpected = sorted(k for k in fields if k not in ALLOWED)
    signature = hashlib.sha256(",".join(fields).encode()).hexdigest()[:10]
    return f"source-v1-{signature}", missing, unexpected

def normalize_timestamp(value: Any) -> str:
    if value is None or str(value).strip() == "":
        raise ValueError("Missing required timestamp")
    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid timestamp") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")

def canonicalize(row: dict[str, Any], source_file: str, run_id: str, ingestion_time: str) -> tuple[dict[str, Any] | None, str | None, str | None, str | None]:
    """Returns normalized record or rejection (category, code, reason)."""
    if row.get("_parse_error"):
        return None, "MALFORMED", "MALFORMED_RECORD", str(row["_parse_error"])
    timestamp = pick(row, "timestamp")
    service, message, severity = pick(row, "service_name"), pick(row, "message"), pick(row, "severity")
    missing = [name for name, value in (("timestamp", timestamp), ("service_name", service), ("message", message), ("severity", severity)) if value is None or str(value).strip() == ""]
    if missing:
        return None, "VALIDATION", "MISSING_REQUIRED_FIELD", "Missing required field(s): " + ", ".join(missing)
    invalid_types = [name for name, value in (("timestamp", timestamp), ("service_name", service), ("message", message), ("severity", severity)) if not isinstance(value, str)]
    if invalid_types:
        return None, "VALIDATION", "INVALID_FIELD_TYPE", "Expected text value(s) for: " + ", ".join(invalid_types)
    event_id_value = pick(row, "event_id")
    if isinstance(event_id_value, (dict, list)):
        return None, "VALIDATION", "INVALID_FIELD_TYPE", "event_id must be a scalar value"
    try:
        event_time = normalize_timestamp(timestamp)
    except ValueError as exc:
        return None, "VALIDATION", "INVALID_TIMESTAMP", str(exc)
    raw_severity = str(severity).strip().upper()
    sev = {"WARN": "WARNING", "FATAL": "CRITICAL"}.get(raw_severity, raw_severity)
    if sev not in SEVERITIES:
        return None, "VALIDATION", "UNKNOWN_SEVERITY", f"Unknown severity '{severity}'"
    latency_raw = pick(row, "latency_ms")
    latency = None
    if latency_raw is not None and str(latency_raw).strip() != "":
        try:
            latency = float(str(latency_raw).lower().removesuffix("ms"))
            if not math.isfinite(latency): raise ValueError
            if latency < 0: return None, "VALIDATION", "NEGATIVE_LATENCY", "Latency cannot be negative"
            if latency.is_integer(): latency = int(latency)
        except ValueError:
            return None, "VALIDATION", "INVALID_LATENCY", f"Invalid latency '{latency_raw}'"
    content = {"event_timestamp": event_time, "severity": sev, "service_name": str(service).strip(), "message": str(message).strip(), "latency_ms": latency}
    fingerprint = hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    eid = event_id_value
    if eid is None or (isinstance(eid, str) and not eid.strip()):
        eid = fingerprint
    _, _, unknown = schema_version(row)
    return ({"event_id": str(eid).strip(), "event_fingerprint": fingerprint, "event_timestamp": event_time, "ingestion_timestamp": ingestion_time, "severity": sev, "raw_severity": str(severity), "service_name": content["service_name"], "message": content["message"], "latency_ms": latency, "source_file": source_file, "source_line": row.get("_source_line"), "run_id": run_id, "raw_payload": row.get("_raw") or json.dumps(row, ensure_ascii=False, default=str), "unexpected_fields": json.dumps(unknown)}, None, None, None)
