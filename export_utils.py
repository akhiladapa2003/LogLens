"""Helpers for making CSV downloads safer to open in spreadsheet software."""
import re

_FORMULA_PREFIX = re.compile(r"^[\x00-\x20]*[=+\-@]")
_NUMERIC_TEXT = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


def spreadsheet_safe_cell(value):
    """Prefix unsafe leading formula/control text without changing database values."""
    if not isinstance(value, str):
        return value

    numeric_text = _NUMERIC_TEXT.fullmatch(value.strip()) is not None
    has_leading_control = bool(value and value[0] in "\t\r\n")
    looks_like_formula = _FORMULA_PREFIX.match(value) is not None
    if not numeric_text and (has_leading_control or looks_like_formula):
        return "'" + value
    return value


def dataframe_to_safe_csv(frame) -> str:
    """Serialize a dataframe to CSV with spreadsheet formula neutralization."""
    return frame.map(spreadsheet_safe_cell).to_csv(index=False)
