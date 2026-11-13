"""Analytics always query persisted SQLite records."""
import re
from contextlib import closing

import pandas as pd

from database import connect


def filter_rejections(rejections: pd.DataFrame, query: str) -> tuple[pd.DataFrame, str | None]:
    """Filter rejection rows using a case-insensitive regex without hiding bad patterns."""
    if not query:
        return rejections.copy(), None
    try:
        pattern = re.compile(query, re.IGNORECASE)
    except re.error as exc:
        return rejections.iloc[0:0].copy(), f"Invalid regular expression: {exc.msg}"

    matches = rejections.astype(str).apply(
        lambda column: column.map(lambda value: pattern.search(value) is not None)
    ).any(axis=1)
    return rejections.loc[matches].copy(), None


def processed_records(db_path="data/loglens.db") -> pd.DataFrame:
    """Return accepted events in a stable order for explicit export requests."""
    with closing(connect(db_path)) as db:
        return pd.read_sql_query(
            "SELECT * FROM processed_logs ORDER BY event_timestamp, event_id", db
        )


def summary(db_path="data/loglens.db"):
    with closing(connect(db_path)) as db:
        total = db.execute("SELECT COUNT(*) FROM processed_logs").fetchone()[0]
        errors = db.execute("SELECT COUNT(*) FROM processed_logs WHERE severity IN ('ERROR','CRITICAL')").fetchone()[0]
        latency = pd.read_sql_query(
            "SELECT latency_ms FROM processed_logs WHERE latency_ms IS NOT NULL", db
        )["latency_ms"]
        result = {
            "total_records": total,
            "accepted_records": total,
            "rejected_records": db.execute(
                "SELECT COUNT(*) FROM rejected_records WHERE category!='DUPLICATE'"
            ).fetchone()[0],
            "duplicate_records": db.execute(
                "SELECT COUNT(*) FROM rejected_records WHERE category='DUPLICATE'"
            ).fetchone()[0],
            "error_records": errors,
            "critical_records": db.execute(
                "SELECT COUNT(*) FROM processed_logs WHERE severity='CRITICAL'"
            ).fetchone()[0],
            "error_rate": 100 * errors / total if total else 0,
            "latency_count": len(latency),
            "average_latency": float(latency.mean()) if len(latency) else None,
            "median_latency": float(latency.median()) if len(latency) else None,
            "p95_latency": float(latency.quantile(.95)) if len(latency) else None,
            "p99_latency": float(latency.quantile(.99)) if len(latency) else None,
            "min_latency": float(latency.min()) if len(latency) else None,
            "max_latency": float(latency.max()) if len(latency) else None,
        }
        result["severity"] = pd.read_sql_query(
            "SELECT severity,COUNT(*) count FROM processed_logs GROUP BY severity ORDER BY severity", db
        )
        result["services"] = pd.read_sql_query(
            "SELECT service_name,COUNT(*) count,SUM(CASE WHEN severity IN ('ERROR','CRITICAL') THEN 1 ELSE 0 END) errors,100.0*SUM(CASE WHEN severity IN ('ERROR','CRITICAL') THEN 1 ELSE 0 END)/COUNT(*) error_rate FROM processed_logs GROUP BY service_name ORDER BY service_name",
            db,
        )
        result["trends"] = pd.read_sql_query(
            "SELECT substr(event_timestamp,1,13) hour,COUNT(*) count,SUM(CASE WHEN severity IN ('ERROR','CRITICAL') THEN 1 ELSE 0 END) errors FROM processed_logs GROUP BY hour ORDER BY hour",
            db,
        )
        result["runs"] = pd.read_sql_query(
            "SELECT * FROM pipeline_runs ORDER BY start_time DESC", db
        )
        result["rejections"] = pd.read_sql_query(
            "SELECT * FROM rejected_records ORDER BY rejection_id DESC", db
        )
        result["observations"] = pd.read_sql_query(
            "SELECT * FROM schema_observations ORDER BY observation_id DESC", db
        )
        return result
