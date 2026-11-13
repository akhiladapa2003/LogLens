"""Explicit dry-run-first retention cleanup for old, completed pipeline runs."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from database import connect

_DEPENDENT_TABLES = ("processed_logs", "rejected_records", "schema_observations", "processed_files")


def prune_old_runs(
    db_path: str | Path,
    older_than_days: int,
    *,
    apply: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Report or remove completed runs older than a retention cutoff.

    Dry-run is the default. Apply deletes child rows before run rows in one
    transaction, preserving foreign-key integrity if any delete fails.
    """
    if not isinstance(older_than_days, int) or isinstance(older_than_days, bool) or older_than_days < 1:
        raise ValueError("older_than_days must be a positive integer")
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    cutoff = (reference.astimezone(timezone.utc) - timedelta(days=older_than_days)).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")

    with closing(connect(db_path)) as db:
        try:
            if apply:
                db.execute("BEGIN IMMEDIATE")
            run_ids = [row[0] for row in db.execute(
                "SELECT run_id FROM pipeline_runs WHERE end_time IS NOT NULL AND end_time < ? ORDER BY run_id",
                (cutoff,),
            )]
            counts = {table: 0 for table in _DEPENDENT_TABLES}
            if run_ids:
                placeholders = ",".join("?" for _ in run_ids)
                for table in _DEPENDENT_TABLES:
                    counts[table] = db.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE run_id IN ({placeholders})", run_ids
                    ).fetchone()[0]
                if apply:
                    for table in _DEPENDENT_TABLES:
                        db.execute(f"DELETE FROM {table} WHERE run_id IN ({placeholders})", run_ids)
                    db.execute(f"DELETE FROM pipeline_runs WHERE run_id IN ({placeholders})", run_ids)
            if apply:
                db.commit()
            else:
                db.rollback()
            return {
                "cutoff_utc": cutoff,
                "older_than_days": older_than_days,
                "dry_run": not apply,
                "candidate_runs": len(run_ids),
                "deleted_runs": len(run_ids) if apply else 0,
                "dependent_rows": counts,
            }
        except Exception:
            db.rollback()
            raise
