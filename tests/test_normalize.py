import pytest
from app.services.normalize import normalize_time, normalize_date, normalize_numeric, normalize_string, normalize_enum


def test_time_hms_strips_seconds():
    assert normalize_time("14:35:22") == "14:35"

def test_time_hm_preserved():
    assert normalize_time("09:05") == "09:05"

def test_time_single_digit_hour():
    assert normalize_time("9:05") == "09:05"

def test_time_none():
    assert normalize_time(None) is None

def test_time_null_string():
    assert normalize_time("null") is None

def test_date_ddmmyyyy():
    assert normalize_date("15/03/2024") == "15/03/2024"

def test_date_ddmmyy_expands():
    assert normalize_date("12/05/25") == "12/05/2025"

def test_date_iso():
    assert normalize_date("2024-03-15") == "15/03/2024"

def test_date_dashes():
    assert normalize_date("15-03-2024") == "15/03/2024"

def test_date_none():
    assert normalize_date(None) is None

def test_numeric_dot():
    assert normalize_numeric("7.5") == 7.5

def test_numeric_comma():
    assert normalize_numeric("7,5") == 7.5

def test_numeric_int():
    assert normalize_numeric(8) == 8.0

def test_numeric_none():
    assert normalize_numeric(None) is None

def test_numeric_space_separated():
    assert normalize_numeric("1 234.5") == 1234.5

def test_string_normalizes_case_and_spaces():
    assert normalize_string("  Béton  de  structure  ") == "béton de structure"

def test_string_none():
    assert normalize_string(None) is None

def test_enum_uppercases():
    assert normalize_enum("c25/30") == "C25/30"

def test_enum_strips_and_normalizes_spaces():
    assert normalize_enum("  XC2  XF1  ") == "XC2 XF1"
