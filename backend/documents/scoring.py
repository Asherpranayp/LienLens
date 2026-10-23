"""Per-field accuracy scoring.

Each extracted field is scored against a reference:
- ground truth, for synthetic bills (exact answer known), else
- the human reviewer's decision (accept = correct, edit = wrong).

Error types: missing, wrong_value, format_error, hallucinated.

We also measure "flag recall": of the fields the model got wrong, how many
did validation/confidence flag for review? That is the number that tells you
whether it is safe to let reviewers skip unflagged fields.
"""

from collections import defaultdict

from .extraction.normalize import normalize_text
from .models import FIELD_LABELS, FIELD_NAMES, Document, ExtractedField

TEXT_FIELDS = {"provider_name", "patient_name"}
ERROR_TYPES = ["missing", "wrong_value", "format_error", "hallucinated"]


def _equal(name: str, a: str, b: str) -> bool:
    if name in TEXT_FIELDS:
        return normalize_text(a) == normalize_text(b)
    return (a or "") == (b or "")


def score_field(field: ExtractedField, ground_truth: dict | None) -> str | None:
    """Return 'correct', an error type, or None if the field can't be scored yet."""
    if ground_truth is not None and field.name in ground_truth:
        truth = ground_truth.get(field.name) or ""
        if not field.value:
            if field.validation_message.startswith("Could not parse"):
                return "format_error"
            return "missing" if truth else "correct"
        if not truth:
            return "hallucinated"
        return "correct" if _equal(field.name, field.value, truth) else "wrong_value"

    if field.review_state == ExtractedField.ReviewState.ACCEPTED:
        return "correct"
    if field.review_state == ExtractedField.ReviewState.EDITED:
        return "missing" if not field.value else "wrong_value"
    return None


def document_scores(document: Document) -> dict:
    run = document.latest_run
    if run is None:
        return {}
    return {f.name: score_field(f, document.ground_truth) for f in run.fields.all()}


def compute_metrics() -> dict:
    per_field = {
        name: {
            "field": name,
            "label": FIELD_LABELS[name],
            "scored": 0,
            "correct": 0,
            "errors": {e: 0 for e in ERROR_TYPES},
        }
        for name in FIELD_NAMES
    }
    per_layout = defaultdict(lambda: {"scored": 0, "correct": 0})
    per_document = []
    wrong_total = wrong_flagged = flagged_total = 0

    documents = Document.objects.prefetch_related("runs__fields")
    for doc in documents:
        run = doc.latest_run
        if run is None or run.status != "succeeded":
            continue
        doc_scored = doc_correct = 0
        layout = (doc.ground_truth or {}).get("layout", "uploaded")
        for f in run.fields.all():
            if f.needs_review:
                flagged_total += 1
            result = score_field(f, doc.ground_truth)
            if result is None:
                continue
            bucket = per_field[f.name]
            bucket["scored"] += 1
            doc_scored += 1
            per_layout[layout]["scored"] += 1
            if result == "correct":
                bucket["correct"] += 1
                doc_correct += 1
                per_layout[layout]["correct"] += 1
            else:
                bucket["errors"][result] += 1
                wrong_total += 1
                if f.needs_review:
                    wrong_flagged += 1
        if doc_scored:
            per_document.append(
                {
                    "id": doc.pk,
                    "name": doc.original_name,
                    "layout": layout,
                    "extractor": run.extractor,
                    "accuracy": round(doc_correct / doc_scored, 4),
                    "scored": doc_scored,
                }
            )

    for bucket in per_field.values():
        bucket["accuracy"] = (
            round(bucket["correct"] / bucket["scored"], 4) if bucket["scored"] else None
        )

    total_scored = sum(b["scored"] for b in per_field.values())
    total_correct = sum(b["correct"] for b in per_field.values())
    return {
        "overall": {
            "documents_scored": len(per_document),
            "fields_scored": total_scored,
            "accuracy": round(total_correct / total_scored, 4) if total_scored else None,
            "fields_flagged_for_review": flagged_total,
            "errors": wrong_total,
            # Of the fields that were wrong, the share that review flagging caught.
            "flag_recall": round(wrong_flagged / wrong_total, 4) if wrong_total else None,
        },
        "per_field": list(per_field.values()),
        "per_layout": [
            {
                "layout": k,
                "scored": v["scored"],
                "accuracy": round(v["correct"] / v["scored"], 4) if v["scored"] else None,
            }
            for k, v in sorted(per_layout.items())
        ],
        "per_document": per_document,
    }
