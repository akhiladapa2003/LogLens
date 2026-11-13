"""Input readers for JSON, JSONL, CSV, and common plain-text log formats."""
from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any

TEXT_PATTERNS = [
    re.compile(r"^(?P<timestamp>\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d)\s+(?P<level>\w+)\s+(?P<service>\S+)\s+(?P<message>.*)$"),
    re.compile(r"^\[(?P<timestamp>[^]]+)\]\s+(?P<level>\w+)\s+(?P<service>\S+)\s+(?P<message>.*)$"),
]
KV = re.compile(r"\b(latency_ms|latency|duration_ms|duration)=([^\s]+)", re.I)


def parse_file(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    suffix = path.suffix.lower()
    raw = path.read_text(encoding="utf-8-sig")
    if suffix == ".csv":
        reader = csv.DictReader(io.StringIO(raw, newline=""))
        records = []
        reader.fieldnames  # Consume the header before tracking data-row line numbers.
        while True:
            try:
                row = next(reader)
            except StopIteration:
                break
            source_line = reader.line_num
            parse_error = "CSV row has more fields than its header" if None in row else None
            records.append({**row, "_source_line": source_line, "_raw": json.dumps(row, ensure_ascii=False, default=str), "_parse_error": parse_error})
        return records
    if suffix in {".jsonl", ".ndjson"}:
        records = []
        for i, line in enumerate(raw.splitlines(), 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                records.append({**item, "_source_line": i, "_raw": line, "_parse_error": None} if isinstance(item, dict) else {"_source_line": i, "_raw": line, "_parse_error": "JSONL record must be an object"})
            except json.JSONDecodeError as exc:
                records.append({"_source_line": i, "_raw": line, "_parse_error": f"Malformed JSON: {exc.msg}"})
        return records
    if suffix == ".json":
        try:
            obj = json.loads(raw)
            items = obj if isinstance(obj, list) else [obj]
            return [{**v, "_source_line": i, "_raw": json.dumps(v, ensure_ascii=False), "_parse_error": None} if isinstance(v, dict) else {"_source_line": i, "_raw": repr(v), "_parse_error": "JSON record must be an object"} for i, v in enumerate(items, 1)]
        except json.JSONDecodeError:
            # Recover JSONL-like content even when the extension is .json.
            return [{"_source_line": i, "_raw": line, "_parse_error": "Malformed JSON"} for i, line in enumerate(raw.splitlines(), 1)]
    if suffix in {".txt", ".log"}:
        records = []
        for i, line in enumerate(raw.splitlines(), 1):
            match = next((p.match(line) for p in TEXT_PATTERNS if p.match(line)), None)
            if not match:
                records.append({"_source_line": i, "_raw": line, "_parse_error": "Unrecognized text log format"})
                continue
            row = match.groupdict()
            for key, value in KV.findall(row["message"]):
                row[key.lower()] = value
            row.update(_source_line=i, _raw=line)
            records.append(row)
        return records
    raise ValueError(f"Unsupported file type '{suffix}'. Use JSON, JSONL, CSV, TXT, or LOG.")
