import io

import pypdfium2 as pdfium
from django.db import transaction
from django.http import FileResponse, HttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from .extraction.normalize import MONEY_FIELDS, normalize_field
from .extraction.validation import check_arithmetic
from .extraction.pipeline import choose_extractor, enqueue_extraction
from .models import Document, ExtractedField, Review
from .scoring import compute_metrics
from .serializers import (
    DocumentDetailSerializer,
    DocumentListSerializer,
    DocumentUploadSerializer,
    ExtractedFieldSerializer,
    ReviewSerializer,
)


class DocumentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    GET    /api/documents/               list documents
    POST   /api/documents/               upload a PDF (multipart: file, optional ground_truth)
    GET    /api/documents/{id}/          document with extracted fields and validation results
    DELETE /api/documents/{id}/          remove a document
    GET    /api/documents/{id}/file/     the original PDF
    GET    /api/documents/{id}/preview/  page 1 rendered as PNG (?page=N for others)
    POST   /api/documents/{id}/reextract/  run extraction again
    """

    queryset = Document.objects.prefetch_related("runs__fields")

    def get_serializer_class(self):
        if self.action == "list":
            return DocumentListSerializer
        return DocumentDetailSerializer

    def create(self, request):
        upload = DocumentUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        f = upload.validated_data["file"]
        document = Document.objects.create(
            file=f,
            original_name=f.name,
            ground_truth=upload.validated_data.get("ground_truth"),
        )
        enqueue_extraction(document)
        document = self.get_queryset().get(pk=document.pk)
        data = DocumentDetailSerializer(document, context={"request": request}).data
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def file(self, request, pk=None):
        document = self.get_object()
        response = FileResponse(document.file.open("rb"), content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{document.original_name}"'
        return response

    @action(detail=True, methods=["get"])
    def preview(self, request, pk=None):
        """First page rendered as PNG, so the review UI works in any browser."""
        document = self.get_object()
        page = int(request.query_params.get("page", 1))
        pdf = pdfium.PdfDocument(document.file.path)
        try:
            if not 1 <= page <= len(pdf):
                return Response({"detail": "Page out of range."}, status=404)
            image = pdf[page - 1].render(scale=2).to_pil()
        finally:
            pdf.close()
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        response = HttpResponse(buffer.getvalue(), content_type="image/png")
        response["Cache-Control"] = "private, max-age=300"
        return response

    @action(detail=True, methods=["post"])
    def reextract(self, request, pk=None):
        document = self.get_object()
        enqueue_extraction(document)
        document = self.get_queryset().get(pk=document.pk)
        return Response(DocumentDetailSerializer(document, context={"request": request}).data)


class FieldViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    GET  /api/fields/{id}/          one extracted field
    POST /api/fields/{id}/review/   record a decision: accept | edit | flag
    """

    queryset = ExtractedField.objects.select_related("run__document")
    serializer_class = ExtractedFieldSerializer

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        field = self.get_object()
        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        decision = serializer.validated_data["decision"]

        with transaction.atomic():
            review = serializer.save(field=field)
            if decision == Review.Decision.ACCEPT:
                field.review_state = ExtractedField.ReviewState.ACCEPTED
                field.final_value = field.value
            elif decision == Review.Decision.EDIT:
                field.review_state = ExtractedField.ReviewState.EDITED
                field.final_value = normalize_field(field.name, review.corrected_value) or (
                    review.corrected_value.strip()
                )
            else:
                field.review_state = ExtractedField.ReviewState.FLAGGED

            # Re-check a human correction too: an edited amount that breaks the
            # bill's arithmetic is flagged instead of silently accepted.
            if decision == Review.Decision.EDIT and field.name in MONEY_FIELDS:
                finals = {f.name: f.final_value for f in field.run.fields.exclude(pk=field.pk)}
                finals[field.name] = field.final_value
                issues, implicated = check_arithmetic(finals, field.run.line_items)
                if field.name in implicated:
                    field.is_valid = False
                    field.validation_message = "Corrected value fails arithmetic check"
                else:
                    field.is_valid = True
                    field.validation_message = ""
            field.save(
                update_fields=["review_state", "final_value", "is_valid", "validation_message"]
            )

            # A document is reviewed once every field has a decision.
            document = field.run.document
            pending = field.run.fields.filter(review_state=ExtractedField.ReviewState.PENDING)
            if not pending.exists():
                document.status = Document.Status.REVIEWED
                document.save(update_fields=["status", "updated_at"])

        return Response(ExtractedFieldSerializer(field).data)


@api_view(["GET"])
def metrics(request):
    return Response(compute_metrics())


@api_view(["GET"])
def health(request):
    return Response({"status": "ok", "extractor": choose_extractor()})
