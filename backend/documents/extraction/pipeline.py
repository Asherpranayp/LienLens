"""Extraction pipeline: text -> extractor -> normalize -> validate -> persist.

`enqueue_extraction` is the single entry point the API calls. In this demo it
runs the job inline. In production it would publish the document id to a queue
(e.g. SQS) and a worker process would call `process_document`; nothing else in
the codebase needs to change for that swap.
"""

import logging
import time

import pdfplumber
from django.conf import settings
from django.db import transaction

from ..models import FIELD_NAMES, Document, ExtractedField, ExtractionRun
from . import llm, rules
from .normalize import normalize_field
from .validation import check_arithmetic, check_field, check_line_items

logger = logging.getLogger("documents")


def extract_text(path: str) -> str:
    with pdfplumber.open(path) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


def choose_extractor() -> str:
    mode = settings.LIENLENS_EXTRACTOR
    if mode == "auto":
        return "llm" if settings.ANTHROPIC_API_KEY else "rules"
    return mode


def run_extractor(text: str, llm_client=None):
    if choose_extractor() == "llm":
        return llm.extract(text, client=llm_client)
    return rules.extract(text)


def process_document(document: Document, llm_client=None) -> ExtractionRun:
    document.status = Document.Status.PROCESSING
    document.error_message = ""
    document.save(update_fields=["status", "error_message", "updated_at"])

    started = time.monotonic()
    try:
        text = extract_text(document.file.path)
        result = run_extractor(text, llm_client=llm_client)
    except Exception as exc:  # noqa: BLE001 - any extractor failure marks the doc failed
        # Log the error type only; never log document text (PHI-safe).
        logger.warning("Extraction failed for document %s: %s", document.pk, type(exc).__name__)
        document.status = Document.Status.FAILED
        document.error_message = f"{type(exc).__name__}: {exc}"[:500]
        document.save(update_fields=["status", "error_message", "updated_at"])
        return ExtractionRun.objects.create(
            document=document,
            extractor=choose_extractor(),
            latency_ms=int((time.monotonic() - started) * 1000),
            status=ExtractionRun.Status.FAILED,
        )
    latency_ms = int((time.monotonic() - started) * 1000)

    normalized = {
        name: normalize_field(name, result.fields[name].value) for name in FIELD_NAMES
    }
    line_issues = check_line_items(result.line_items)
    math_issues, implicated = check_arithmetic(normalized, result.line_items)

    with transaction.atomic():
        run = ExtractionRun.objects.create(
            document=document,
            extractor=result.extractor,
            model_name=result.model_name,
            prompt_version=result.prompt_version,
            latency_ms=latency_ms,
            status=ExtractionRun.Status.SUCCEEDED,
            line_items=result.line_items,
            validation_issues=line_issues + math_issues,
        )
        for name in FIELD_NAMES:
            guess = result.fields[name]
            check = check_field(name, normalized[name], guess.value)
            message = check.message
            if check.is_valid and name in implicated:
                message = "Fails cross-field arithmetic check"
            low_confidence = guess.confidence < settings.LIENLENS_LOW_CONFIDENCE
            ExtractedField.objects.create(
                run=run,
                name=name,
                value=normalized[name],
                confidence=round(guess.confidence, 3),
                is_valid=check.is_valid and name not in implicated,
                validation_message=message,
                needs_review=(not check.is_valid) or name in implicated or low_confidence,
                final_value=normalized[name],
            )
        document.status = Document.Status.NEEDS_REVIEW
        document.save(update_fields=["status", "updated_at"])

    logger.info(
        "Extracted document %s with %s in %sms", document.pk, result.extractor, latency_ms
    )
    return run


def enqueue_extraction(document: Document) -> None:
    """Hand a document to the extraction worker. Inline for the demo."""
    process_document(document)
