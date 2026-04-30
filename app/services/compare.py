from typing import Any

from app.domain.models import FieldType
from app.services.normalize import (
    normalize_date,
    normalize_enum,
    normalize_numeric,
    normalize_string,
    normalize_time,
    to_str,
)


STATUS_MATCH = "MATCH"
STATUS_MISMATCH = "MISMATCH"
STATUS_MISSING = "MISSING"
STATUS_GT_EMPTY = "GT_EMPTY"
STATUS_SKIPPED = "SKIPPED"


def compare_field(gt_value: Any, extracted_value: Any, field_type: FieldType, *, name: str = "") -> str:
    """Return MATCH / MISMATCH / MISSING / GT_EMPTY for one field."""
    if field_type == FieldType.NUMERIC:
        gt_num = normalize_numeric(gt_value)
        if gt_num is None:
            return STATUS_GT_EMPTY
    else:
        if to_str(gt_value) is None:
            return STATUS_GT_EMPTY

    if extracted_value is None or (
        isinstance(extracted_value, str) and extracted_value.strip().lower() in ("", "null", "none", "n/a")
    ):
        return STATUS_MISSING

    if field_type == FieldType.TIME:
        gt_n = normalize_time(gt_value)
        ex_n = normalize_time(extracted_value)
        if gt_n is None:
            return STATUS_GT_EMPTY
        return STATUS_MATCH if gt_n == ex_n else STATUS_MISMATCH

    if field_type == FieldType.DATE:
        gt_n = normalize_date(gt_value)
        ex_n = normalize_date(extracted_value)
        if gt_n is None:
            return STATUS_GT_EMPTY
        return STATUS_MATCH if gt_n == ex_n else STATUS_MISMATCH

    if field_type == FieldType.NUMERIC:
        gt_n = normalize_numeric(gt_value)
        ex_n = normalize_numeric(extracted_value)
        if ex_n is None:
            return STATUS_MISSING
        tolerance = 0.1 if "carbone" in name.lower() else 0.01
        return STATUS_MATCH if abs((gt_n or 0) - ex_n) <= tolerance else STATUS_MISMATCH

    if field_type == FieldType.BOOLEAN:
        gt_n = to_str(gt_value)
        ex_n = to_str(extracted_value)
        if gt_n is None:
            return STATUS_GT_EMPTY
        if ex_n is None:
            return STATUS_MISSING
        return STATUS_MATCH if gt_n.lower() == ex_n.lower() else STATUS_MISMATCH

    if field_type == FieldType.ENUM:
        gt_n = normalize_enum(gt_value)
        ex_n = normalize_enum(extracted_value)
        if gt_n is None:
            return STATUS_GT_EMPTY
        if ex_n is None:
            return STATUS_MISSING
        if gt_n == ex_n:
            return STATUS_MATCH
        if ex_n.startswith(gt_n) or gt_n.startswith(ex_n):
            return STATUS_MATCH
        return STATUS_MISMATCH

    # FieldType.STRING
    gt_n = normalize_string(gt_value)
    ex_n = normalize_string(extracted_value)
    if gt_n is None:
        return STATUS_GT_EMPTY
    if ex_n is None:
        return STATUS_MISSING
    if gt_n == ex_n:
        return STATUS_MATCH
    if gt_n in ex_n or ex_n in gt_n:
        return STATUS_MATCH
    return STATUS_MISMATCH
