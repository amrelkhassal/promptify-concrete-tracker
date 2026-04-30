import pytest
from app.domain.models import FieldType
from app.services.compare import (
    compare_field,
    STATUS_MATCH,
    STATUS_MISMATCH,
    STATUS_MISSING,
    STATUS_GT_EMPTY,
)


# ── TIME ──────────────────────────────────────────────────────────────────────

def test_time_match():
    assert compare_field("14:35:00", "14:35", FieldType.TIME) == STATUS_MATCH

def test_time_mismatch():
    assert compare_field("14:35", "14:36", FieldType.TIME) == STATUS_MISMATCH

def test_time_missing():
    assert compare_field("14:35", None, FieldType.TIME) == STATUS_MISSING

def test_time_gt_empty():
    assert compare_field(None, "14:35", FieldType.TIME) == STATUS_GT_EMPTY

# ── DATE ──────────────────────────────────────────────────────────────────────

def test_date_match_iso_vs_dmy():
    assert compare_field("2024-03-15", "15/03/2024", FieldType.DATE) == STATUS_MATCH

def test_date_mismatch():
    assert compare_field("15/03/2024", "16/03/2024", FieldType.DATE) == STATUS_MISMATCH

def test_date_gt_empty():
    assert compare_field(None, "15/03/2024", FieldType.DATE) == STATUS_GT_EMPTY

# ── NUMERIC ───────────────────────────────────────────────────────────────────

def test_numeric_match_epsilon():
    assert compare_field("7.5", "7.5", FieldType.NUMERIC) == STATUS_MATCH

def test_numeric_comma_decimal():
    assert compare_field("7,5", "7.5", FieldType.NUMERIC) == STATUS_MATCH

def test_numeric_mismatch():
    assert compare_field("7.5", "8.0", FieldType.NUMERIC) == STATUS_MISMATCH

def test_numeric_carbone_tolerance():
    # carboneWeight allows ±0.1
    assert compare_field("123.8", "123.85", FieldType.NUMERIC, name="carboneWeight") == STATUS_MATCH

def test_numeric_gt_empty():
    assert compare_field(None, "7.5", FieldType.NUMERIC) == STATUS_GT_EMPTY

def test_numeric_missing():
    assert compare_field("7.5", None, FieldType.NUMERIC) == STATUS_MISSING

# ── ENUM ──────────────────────────────────────────────────────────────────────

def test_enum_exact_match():
    assert compare_field("XC2", "XC2", FieldType.ENUM) == STATUS_MATCH

def test_enum_case_insensitive():
    assert compare_field("XC2", "xc2", FieldType.ENUM) == STATUS_MATCH

def test_enum_partial_prefix():
    # extracted "XC2 XF1" while GT is "XC2" → starts-with match
    assert compare_field("XC2", "XC2 XF1", FieldType.ENUM) == STATUS_MATCH

def test_enum_mismatch():
    assert compare_field("XC2", "XC3", FieldType.ENUM) == STATUS_MISMATCH

def test_enum_missing():
    assert compare_field("XC2", None, FieldType.ENUM) == STATUS_MISSING

# ── STRING ────────────────────────────────────────────────────────────────────

def test_string_match_normalized():
    assert compare_field("  C25/30  ", "c25/30", FieldType.STRING) == STATUS_MATCH

def test_string_contains_match():
    assert compare_field("C25/30", "Béton C25/30 XC2", FieldType.STRING) == STATUS_MATCH

def test_string_mismatch():
    assert compare_field("C25/30", "C30/37", FieldType.STRING) == STATUS_MISMATCH

def test_string_gt_empty():
    assert compare_field("", "something", FieldType.STRING) == STATUS_GT_EMPTY

# ── BOOLEAN ───────────────────────────────────────────────────────────────────

def test_boolean_match():
    assert compare_field("true", "true", FieldType.BOOLEAN) == STATUS_MATCH

def test_boolean_case_insensitive():
    assert compare_field("True", "true", FieldType.BOOLEAN) == STATUS_MATCH

def test_boolean_mismatch():
    assert compare_field("true", "false", FieldType.BOOLEAN) == STATUS_MISMATCH

def test_boolean_missing():
    assert compare_field("true", None, FieldType.BOOLEAN) == STATUS_MISSING
