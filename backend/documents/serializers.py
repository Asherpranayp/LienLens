import json

from rest_framework import serializers

from .models import FIELD_LABELS, Document, ExtractedField, ExtractionRun, Review
from .scoring import document_scores

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ["id", "decision", "corrected_value", "note", "reviewer", "created_at"]
        read_only_fields = ["id", "reviewer", "created_at"]

    def validate(self, attrs):
        if attrs["decision"] == Review.Decision.EDIT and not attrs.get("corrected_value", "").strip():
            raise serializers.ValidationError({"corrected_value": "Required when editing."})
        return attrs


class ExtractedFieldSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()
    score = serializers.SerializerMethodField()

    class Meta:
        model = ExtractedField
        fields = [
            "id",
            "name",
            "label",
            "value",
            "final_value",
            "confidence",
            "is_valid",
            "validation_message",
            "needs_review",
            "review_state",
            "score",
        ]

    def get_label(self, obj):
        return FIELD_LABELS.get(obj.name, obj.name)

    def get_score(self, obj):
        return self.context.get("scores", {}).get(obj.name)


class ExtractionRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExtractionRun
        fields = [
            "id",
            "extractor",
            "model_name",
            "prompt_version",
            "latency_ms",
            "status",
            "line_items",
            "validation_issues",
            "created_at",
        ]


class DocumentListSerializer(serializers.ModelSerializer):
    extractor = serializers.SerializerMethodField()
    fields_to_review = serializers.SerializerMethodField()
    accuracy = serializers.SerializerMethodField()
    layout = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "original_name",
            "status",
            "created_at",
            "extractor",
            "fields_to_review",
            "accuracy",
            "layout",
        ]

    def get_extractor(self, obj):
        run = obj.latest_run
        return run.extractor if run else None

    def get_fields_to_review(self, obj):
        run = obj.latest_run
        if not run:
            return 0
        return sum(
            1
            for f in run.fields.all()
            if f.needs_review and f.review_state == ExtractedField.ReviewState.PENDING
        )

    def get_accuracy(self, obj):
        scores = [s for s in document_scores(obj).values() if s is not None]
        if not scores:
            return None
        return round(sum(s == "correct" for s in scores) / len(scores), 4)

    def get_layout(self, obj):
        return (obj.ground_truth or {}).get("layout")


class DocumentDetailSerializer(DocumentListSerializer):
    run = serializers.SerializerMethodField()
    extracted_fields = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    has_ground_truth = serializers.SerializerMethodField()

    class Meta(DocumentListSerializer.Meta):
        fields = DocumentListSerializer.Meta.fields + [
            "error_message",
            "run",
            "extracted_fields",
            "file_url",
            "has_ground_truth",
        ]

    def get_run(self, obj):
        run = obj.latest_run
        return ExtractionRunSerializer(run).data if run else None

    def get_extracted_fields(self, obj):
        run = obj.latest_run
        if not run:
            return []
        order = {name: i for i, name in enumerate(FIELD_LABELS)}
        items = sorted(run.fields.all(), key=lambda f: order.get(f.name, 99))
        return ExtractedFieldSerializer(
            items, many=True, context={"scores": document_scores(obj)}
        ).data

    def get_file_url(self, obj):
        request = self.context.get("request")
        path = f"/api/documents/{obj.pk}/file/"
        return request.build_absolute_uri(path) if request else path

    def get_has_ground_truth(self, obj):
        return obj.ground_truth is not None


class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    ground_truth = serializers.CharField(required=False, allow_blank=True)

    def validate_file(self, f):
        if not f.name.lower().endswith(".pdf"):
            raise serializers.ValidationError("Only PDF files are supported.")
        if f.size > MAX_UPLOAD_BYTES:
            raise serializers.ValidationError("File is larger than 10 MB.")
        return f

    def validate_ground_truth(self, raw):
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise serializers.ValidationError("ground_truth must be valid JSON.") from exc
        if not isinstance(data, dict):
            raise serializers.ValidationError("ground_truth must be a JSON object.")
        return data
