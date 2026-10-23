"""Normalize raw extracted strings into canonical forms so values can be
validated and compared against ground truth."""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

DATE_FORMATS = ["%m/%d/%Y", "%m/%d/%y", "%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%m-%d-%Y"]


def normalize_money(raw: str | None) -> str | None:
    """'$1,234.50' -> '1234.50'. Returns None if it isn't a number."""
    if raw is None:
        return None
    cleaned = re.sub(r"[^\d.\-]", "", str(raw))
    if not cleaned:
        return None
    try:
        return f"{Decimal(cleaned):.2f}"
    except InvalidOperation:
        return None


def normalize_date(raw: str | None) -> str | None:
    """Any supported date format -> ISO 'YYYY-MM-DD'."""
    if not raw:
        return None
    text = str(raw).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def normalize_text(raw: str | None) -> str:
    """Case-, whitespace-, and punctuation-insensitive form for name comparison."""
    if not raw:
        return ""
    text = re.sub(r"[^\w\s]", " ", str(raw).lower())
    return " ".join(text.split())


def normalize_digits(raw: str | None) -> str:
    return re.sub(r"\D", "", str(raw or ""))


MONEY_FIELDS = {"total_billed", "adjustments", "balance_due"}


def normalize_field(name: str, raw: str | None) -> str:
    """Canonical string for a named field ('' when missing or unparseable)."""
    if raw in (None, ""):
        return ""
    if name in MONEY_FIELDS:
        return normalize_money(raw) or ""
    if name == "date_of_service":
        return normalize_date(raw) or ""
    if name == "provider_npi":
        return normalize_digits(raw)
    return " ".join(str(raw).split())
