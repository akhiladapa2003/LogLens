import csv
import io
import json
import sqlite3
import sys

import pandas as pd
import pytest

import cli
from analytics import filter_rejections
from export_utils import dataframe_to_safe_csv, spreadsheet_safe_cell
from pipeline import run_pipeline


@pytest.mark.parametrize("query", ["(", "[", "*"])
def test_rejection_search_reports_invalid_regex(query):
    records = pd.DataFrame({"rejection_reason": ["invalid timestamp", "unknown severity"]})

    result, error = filter_rejections(records, query)

    assert result.empty
    assert error is not None and "Invalid regular expression" in error


def test_rejection_search_valid_regex_is_case_insensitive():
    records = pd.DataFrame({"rejection_code": ["INVALID_TIMESTAMP", "UNKNOWN_SEVERITY", "OTHER"]})

    result, error = filter_rejections(records, r"invalid_timestamp|unknown_severity")

    assert error is None
    assert result["rejection_code"].tolist() == ["INVALID_TIMESTAMP", "UNKNOWN_SEVERITY"]


def test_rejection_search_empty_query_returns_all_rows():
    records = pd.DataFrame({"rejection_reason": ["one", "two"]})

    result, error = filter_rejections(records, "")

    assert error is None
    pd.testing.assert_frame_equal(result, records)


def test_rejection_search_escaped_special_characters():
    records = pd.DataFrame({"rejection_reason": ["bad code[12]+tag", "ordinary text"]})

    result, error = filter_rejections(records, r"code\[\d+\]\+tag")

    assert error is None
    assert result["rejection_reason"].tolist() == ["bad code[12]+tag"]


@pytest.mark.parametrize(
    "value",
    [
        "=HYPERLINK(\"https://example.invalid\",\"open\")",
        "+SUM(1,2)",
        "-1+2",
        "@SUM(A1:A2)",
        "\t=1+1",
        "\r=1+1",
        "\n=1+1",
    ],
)
def test_spreadsheet_safe_cell_neutralizes_formula_prefixes(value):
    assert spreadsheet_safe_cell(value) == "'" + value


@pytest.mark.parametrize("value", ["ordinary message", "-12", "+12.5", 0, -12, 12.5, None])
def test_spreadsheet_safe_cell_preserves_safe_text_and_numbers(value):
    assert spreadsheet_safe_cell(value) == value


def test_dataframe_csv_is_safe_and_does_not_mutate_or_change_json():
    original = pd.DataFrame({"message": ["=HYPERLINK(\"https://example.invalid\")", "normal"], "latency_ms": [-2, 0]})

    exported = dataframe_to_safe_csv(original)
    rows = list(csv.DictReader(io.StringIO(exported)))

    assert rows[0]["message"].startswith("'=HYPERLINK(")
    assert rows[0]["latency_ms"] == "-2"
    assert original.loc[0, "message"].startswith("=HYPERLINK(")
    assert json.loads(original.to_json(orient="records"))[0]["message"].startswith("=HYPERLINK(")


def test_cli_processed_csv_is_safe_without_changing_database_value(tmp_path, monkeypatch, capsys):
    source = tmp_path / "formula.jsonl"
    original_message = '=HYPERLINK("https://example.invalid","open")'
    source.write_text(json.dumps({
        "event_id": "formula-1",
        "timestamp": "2026-11-13T00:00:00Z",
        "level": "INFO",
        "service": "audit",
        "message": original_message,
    }) + "\n", encoding="utf-8")
    db_path = tmp_path / "db.sqlite"
    result = run_pipeline(source, db_path)
    assert result["accepted_count"] == 1

    output_path = tmp_path / "processed.csv"
    monkeypatch.setattr(sys, "argv", ["cli", "export", "processed", "--db", str(db_path), "--output", str(output_path)])
    cli.main()
    capsys.readouterr()

    with output_path.open(encoding="utf-8", newline="") as exported:
        rows = list(csv.DictReader(exported))
    assert rows[0]["message"] == "'" + original_message
    with sqlite3.connect(db_path) as db:
        stored = db.execute("SELECT message FROM processed_logs WHERE event_id='formula-1'").fetchone()[0]
    assert stored == original_message
