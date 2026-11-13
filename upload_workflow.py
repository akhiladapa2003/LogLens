"""Streamlit upload workflow helpers, kept small and independently testable."""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Any

from pipeline import run_pipeline


def upload_digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def process_uploaded_file(
    uploaded: Any,
    db_path: str | Path,
    processed_hashes: set[str],
) -> tuple[dict[str, Any] | None, str, bool]:
    """Process an uploaded file once per session and preserve its basename.

    Returns (result, content_digest, was_already_processed). Failed runs do
    not enter the session guard, so a corrected/retried upload remains possible.
    """
    content = uploaded.getvalue()
    digest = upload_digest(content)
    if digest in processed_hashes:
        return None, digest, True

    basename = Path(uploaded.name).name
    with tempfile.TemporaryDirectory(prefix="loglens_") as upload_dir:
        upload_path = Path(upload_dir) / basename
        upload_path.write_bytes(content)
        result = run_pipeline(upload_path, db_path)

    if result["status"] != "FAILED":
        processed_hashes.add(digest)
    return result, digest, False
