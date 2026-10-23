from django.contrib import admin

from .models import Document, ExtractedField, ExtractionRun, Review


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["id", "original_name", "status", "created_at"]
    list_filter = ["status"]


@admin.register(ExtractionRun)
class ExtractionRunAdmin(admin.ModelAdmin):
    list_display = ["id", "document", "extractor", "status", "latency_ms", "created_at"]


@admin.register(ExtractedField)
class ExtractedFieldAdmin(admin.ModelAdmin):
    list_display = ["id", "run", "name", "value", "confidence", "needs_review", "review_state"]
    list_filter = ["name", "needs_review", "review_state"]


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ["id", "field", "decision", "reviewer", "created_at"]
