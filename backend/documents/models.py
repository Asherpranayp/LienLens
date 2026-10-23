"""Data model for LienLens.

Document          an uploaded medical bill
ExtractionRun     one pass of the extractor over a document (model, latency, raw output)
ExtractedField    one structured field from a run, with confidence and validation result
Review            a reviewer's decision on a field (accept / edit / flag)
"""

from django.db import models

# The scalar fields LienLens extracts from every bill, in display order.
FIELD_NAMES = [
    "provider_name",
    "provider_npi",
    "patient_name",
    "date_of_service",
    "total_billed",
    "adjustments",
    "balance_due",
]

FIELD_LABELS = {
    "provider_name": "Provider name",
    "provider_npi": "Provider NPI",
    "patient_name": "Patient name",
    "date_of_service": "Date of service",
    "total_billed": "Total billed",
    "adjustments": "Adjustments",
    "balance_due": "Balance due",
}


class Document(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        NEEDS_REVIEW = "needs_review", "Needs review"
        REVIEWED = "reviewed", "Reviewed"
        FAILED = "failed", "Failed"

    file = models.FileField(upload_to="bills/")
    original_name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    # Ground truth is only present for synthetic bills; it powers accuracy scoring.
    ground_truth = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status"])]

    def __str__(self):
        return f"Document {self.pk}: {self.original_name}"

    @property
    def latest_run(self):
        # Relies on ExtractionRun's default ordering so prefetched runs are reused.
        return next(iter(self.runs.all()), None)


class ExtractionRun(models.Model):
    class Status(models.TextChoices):
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="runs")
    extractor = models.CharField(max_length=50)  # "llm" or "rules"
    model_name = models.CharField(max_length=100, blank=True)
    prompt_version = models.CharField(max_length=20, blank=True)
    latency_ms = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices)
    line_items = models.JSONField(default=list)
    validation_issues = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class ExtractedField(models.Model):
    class ReviewState(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        EDITED = "edited", "Edited"
        FLAGGED = "flagged", "Flagged"

    run = models.ForeignKey(ExtractionRun, on_delete=models.CASCADE, related_name="fields")
    name = models.CharField(max_length=50)
    value = models.TextField(blank=True)  # what the model extracted
    confidence = models.FloatField(default=0.0)
    is_valid = models.BooleanField(default=True)
    validation_message = models.CharField(max_length=255, blank=True)
    needs_review = models.BooleanField(default=False)
    review_state = models.CharField(
        max_length=20, choices=ReviewState.choices, default=ReviewState.PENDING
    )
    final_value = models.TextField(blank=True)  # value after human review

    class Meta:
        unique_together = [("run", "name")]

    def __str__(self):
        return f"{self.name}={self.value!r}"


class Review(models.Model):
    class Decision(models.TextChoices):
        ACCEPT = "accept", "Accept"
        EDIT = "edit", "Edit"
        FLAG = "flag", "Flag"

    field = models.ForeignKey(ExtractedField, on_delete=models.CASCADE, related_name="reviews")
    decision = models.CharField(max_length=10, choices=Decision.choices)
    corrected_value = models.TextField(blank=True)
    note = models.CharField(max_length=255, blank=True)
    reviewer = models.CharField(max_length=100, default="demo-reviewer")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
