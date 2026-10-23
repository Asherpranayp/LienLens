"""Validation: checks that catch extractions that are well-formed but wrong.

Three layers:
1. Format checks per field (dates parse, money parses, NPI passes its checksum).
2. Line-item checks (CPT/HCPCS code pattern, amounts parse).
3. Cross-field arithmetic (line items sum to total; total - adjustments = balance).
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .normalize import MONEY_FIELDS, normalize_money

CODE_PATTERN = re.compile(r"^(\d{5}|[A-Z]\d{4})$")


@dataclass
class FieldCheck:
    is_valid: bool
    message: str = ""


def npi_is_valid(npi: str) -> bool:
    """NPI checksum: Luhn algorithm over '80840' + the 10 digits."""
    if not re.fullmatch(r"\d{10}", npi or ""):
        return False
    digits = "80840" + npi
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def check_field(name: str, normalized: str, raw: str | None) -> FieldCheck:
    if not normalized:
        if raw:
            return FieldCheck(False, f"Could not parse '{raw}'")
        return FieldCheck(False, "Missing")
    if name == "provider_npi" and not npi_is_valid(normalized):
        return FieldCheck(False, "NPI fails checksum")
    if name == "date_of_service" and date.fromisoformat(normalized) > date.today():
        return FieldCheck(False, "Date is in the future")
    if name in MONEY_FIELDS and Decimal(normalized) < 0:
        return FieldCheck(False, "Negative amount")
    return FieldCheck(True)


def check_line_items(line_items: list[dict]) -> list[str]:
    issues = []
    for i, item in enumerate(line_items, start=1):
        if not CODE_PATTERN.match(str(item.get("code", ""))):
            issues.append(f"Line {i}: '{item.get('code')}' is not a valid CPT/HCPCS code")
        if normalize_money(item.get("amount")) is None:
            issues.append(f"Line {i}: amount '{item.get('amount')}' is not a number")
    return issues


def check_arithmetic(values: dict[str, str], line_items: list[dict]) -> tuple[list[str], set[str]]:
    """Returns (issues, field names implicated)."""
    issues, implicated = [], set()
    total = values.get("total_billed")
    adj = values.get("adjustments")
    bal = values.get("balance_due")

    amounts = [normalize_money(i.get("amount")) for i in line_items]
    if total and line_items and all(amounts):
        line_sum = sum(Decimal(a) for a in amounts)
        if line_sum != Decimal(total):
            issues.append(f"Line items sum to {line_sum:.2f}, but total billed is {total}")
            implicated.add("total_billed")

    if total and adj and bal:
        expected = Decimal(total) - Decimal(adj)
        if expected != Decimal(bal):
            issues.append(f"Total minus adjustments is {expected:.2f}, but balance due is {bal}")
            implicated.update({"adjustments", "balance_due"})

    return issues, implicated
