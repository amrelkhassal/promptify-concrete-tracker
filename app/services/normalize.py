import re
import unicodedata
from datetime import date, datetime
from datetime import time as dt_time
from typing import Any, Optional


def to_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, bool):
        return str(v).lower()
    s = str(v).strip()
    if s.lower() in ("", "none", "null", "n/a", "na", "-"):
        return None
    return s


def normalize_time(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return f"{v.hour:02d}:{v.minute:02d}"
    if isinstance(v, dt_time):
        return f"{v.hour:02d}:{v.minute:02d}"
    s = to_str(v)
    if s is None:
        return None
    m = re.match(r"^(\d{1,2}):(\d{2})(?::\d{2})?$", s)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return s


def normalize_date(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    s = to_str(v)
    if s is None:
        return None
    m = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})$", s)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        if len(y) == 2:
            y = "20" + y
        return f"{int(d):02d}/{int(mo):02d}/{y}"
    m = re.match(r"^(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})$", s)
    if m:
        y, mo, d = m.group(1), m.group(2), m.group(3)
        return f"{int(d):02d}/{int(mo):02d}/{y}"
    return s


def normalize_numeric(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = to_str(v)
    if s is None:
        return None
    s = s.replace(",", ".").replace(" ", "")
    try:
        return float(s)
    except ValueError:
        return None


def normalize_string(v: Any) -> Optional[str]:
    s = to_str(v)
    if s is None:
        return None
    s = unicodedata.normalize("NFC", s)
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def normalize_enum(v: Any) -> Optional[str]:
    s = to_str(v)
    if s is None:
        return None
    s = unicodedata.normalize("NFC", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s.upper()
