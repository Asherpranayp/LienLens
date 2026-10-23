"""Rule-based extractor: label patterns + regexes.

This is the offline fallback (no API key needed). It is intentionally a
realistic baseline: it handles common labels well and misses unfamiliar ones,
which is exactly the gap an LLM extractor is meant to close. Accuracy scoring
makes that gap visible.
"""

import re

from .base import ExtractionResult, FieldGuess

MONEY = r"\$?\s*([\d,]+\.\d{2})"
CODE = r"(\d{5}|[A-Z]\d{4})"

LABELS = {
    "provider_npi": [r"\bNPI\b[^\d]{0,5}(\d{10})"],
    "patient_name": [
        r"Patient(?:\s*Name)?\s*:\s*([A-Za-z][A-Za-z .'\-]+)",
        r"Patient\s+Name\s*:\s*([A-Za-z][A-Za-z .'\-]+)",
    ],
    "date_of_service": [
        r"Date of Service\s*:\s*([\d/]{8,10})",
        r"Service Date\s*:\s*([A-Za-z]+ \d{1,2}, \d{4})",
    ],
    "total_billed": [r"Total Charges\s*:\s*" + MONEY, r"Total Billed\s*:\s*" + MONEY],
    "adjustments": [r"Adjustments?\s*:\s*" + MONEY],
    "balance_due": [r"Balance Due\s*:\s*" + MONEY],
}

PROVIDER_LABEL = r"(?:Billing\s+)?Provider\s*:\s*(.+)"
HEADER_WORDS = ("STATEMENT", "INVOICE", "BILL")


def _first_match(patterns, text):
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def extract(text: str) -> ExtractionResult:
    fields: dict[str, FieldGuess] = {}

    for name, patterns in LABELS.items():
        value = _first_match(patterns, text)
        fields[name] = FieldGuess(value, 0.95 if value else 0.0)

    # Provider: an explicit label is reliable; otherwise guess the first line
    # that isn't a document title.
    labeled = _first_match([PROVIDER_LABEL], text)
    if labeled:
        fields["provider_name"] = FieldGuess(labeled, 0.95)
    else:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        guess = next((ln for ln in lines if not any(w in ln.upper() for w in HEADER_WORDS)), None)
        fields["provider_name"] = FieldGuess(guess, 0.6 if guess else 0.0)

    # Line items: "<code> <description> $<amount>" on one line.
    line_items = []
    for m in re.finditer(rf"^\s*{CODE}\s+(.+?)\s+{MONEY}\s*$", text, flags=re.MULTILINE):
        line_items.append(
            {"code": m.group(1), "description": m.group(2).strip(), "amount": m.group(3)}
        )

    return ExtractionResult(fields=fields, line_items=line_items, extractor="rules")
