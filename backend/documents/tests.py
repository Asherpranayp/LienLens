import json
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .extraction import llm, rules
from .extraction.normalize import normalize_date, normalize_field, normalize_money
from .extraction.pipeline import extract_text, process_document
from .extraction.validation import check_arithmetic, check_line_items, npi_is_valid
from .models import Document, ExtractedField
from .scoring import compute_metrics
from .synthetic import generate, make_npi

MEDIA = tempfile.mkdtemp()


class NormalizeTests(TestCase):
    def test_money(self):
        self.assertEqual(normalize_money("$1,234.5"), "1234.50")
        self.assertIsNone(normalize_money("n/a"))

    def test_dates(self):
        for raw in ["06/11/2026", "June 11, 2026", "2026-06-11"]:
            self.assertEqual(normalize_date(raw), "2026-06-11")
        self.assertIsNone(normalize_date("sometime in June"))

    def test_npi_digits(self):
        self.assertEqual(normalize_field("provider_npi", "NPI #123-456-7890"), "1234567890")


class ValidationTests(TestCase):
    def test_npi_checksum(self):
        import random

        rng = random.Random(1)
        for _ in range(50):
            self.assertTrue(npi_is_valid(make_npi(rng)))
        self.assertTrue(npi_is_valid("1234567893"))  # CMS published example
        self.assertFalse(npi_is_valid("1234567890"))

    def test_line_items_sum_must_match_total(self):
        items = [{"code": "99213", "amount": "100.00"}, {"code": "72110", "amount": "50.00"}]
        issues, implicated = check_arithmetic(
            {"total_billed": "160.00", "adjustments": "0.00", "balance_due": "160.00"}, items
        )
        self.assertEqual(len(issues), 1)
        self.assertIn("total_billed", implicated)

    def test_balance_must_equal_total_minus_adjustments(self):
        issues, implicated = check_arithmetic(
            {"total_billed": "100.00", "adjustments": "10.00", "balance_due": "100.00"}, []
        )
        self.assertEqual(implicated, {"adjustments", "balance_due"})

    def test_bad_cpt_code(self):
        issues = check_line_items([{"code": "ABCDE", "amount": "10.00"}])
        self.assertEqual(len(issues), 1)


class SyntheticExtractionTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = Path(tempfile.mkdtemp())
        cls.bills = generate(cls.tmp, 3, seed=5)  # one of each layout

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        super().tearDownClass()

    def test_rules_get_layout_a_fully_right(self):
        path, truth = self.bills[0]
        result = rules.extract(extract_text(str(path)))
        for name in ["provider_npi", "patient_name", "total_billed", "balance_due"]:
            self.assertEqual(
                normalize_field(name, result.fields[name].value), truth[name], name
            )
        self.assertEqual(len(result.line_items), len(truth["line_items"]))

    def test_rules_miss_unfamiliar_labels_in_layout_c(self):
        path, truth = self.bills[2]
        result = rules.extract(extract_text(str(path)))
        self.assertIsNone(result.fields["balance_due"].value)  # "Please Pay" isn't known


class FakeLLMClient:
    """Stands in for anthropic.Anthropic so the LLM path is tested offline."""

    def __init__(self, tool_input):
        self.tool_input = tool_input
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input=self.tool_input)])


@override_settings(MEDIA_ROOT=MEDIA)
class PipelineAndApiTests(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.path, self.truth = generate(self.tmp, 3, seed=9)[2]  # layout C
        self.client = APIClient()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _upload(self):
        with open(self.path, "rb") as fh:
            upload = SimpleUploadedFile(self.path.name, fh.read(), content_type="application/pdf")
        return self.client.post(
            "/api/documents/",
            {"file": upload, "ground_truth": json.dumps(self.truth)},
            format="multipart",
        )

    def test_upload_extracts_and_flags_missing_fields(self):
        response = self._upload()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "needs_review")
        fields = {f["name"]: f for f in body["extracted_fields"]}
        self.assertTrue(fields["balance_due"]["needs_review"])
        self.assertEqual(fields["balance_due"]["score"], "missing")
        self.assertEqual(fields["provider_npi"]["score"], "correct")

    def test_preview_renders_png(self):
        doc_id = self._upload().json()["id"]
        r = self.client.get(f"/api/documents/{doc_id}/preview/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/png")
        self.assertEqual(self.client.get(f"/api/documents/{doc_id}/preview/?page=9").status_code, 404)

    def test_rejects_non_pdf(self):
        upload = SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")
        response = self.client.post("/api/documents/", {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_review_flow_marks_document_reviewed(self):
        doc_id = self._upload().json()["id"]
        detail = self.client.get(f"/api/documents/{doc_id}/").json()
        for f in detail["extracted_fields"]:
            if f["value"]:
                payload = {"decision": "accept"}
            else:
                payload = {"decision": "edit", "corrected_value": self.truth[f["name"]]}
            r = self.client.post(f"/api/fields/{f['id']}/review/", payload, format="json")
            self.assertEqual(r.status_code, 200, r.content)
        detail = self.client.get(f"/api/documents/{doc_id}/").json()
        self.assertEqual(detail["status"], "reviewed")
        balance = next(f for f in detail["extracted_fields"] if f["name"] == "balance_due")
        self.assertEqual(balance["final_value"], self.truth["balance_due"])

    def test_wrong_correction_is_caught_by_arithmetic(self):
        doc_id = self._upload().json()["id"]
        fields = ExtractedField.objects.filter(run__document_id=doc_id)
        # Reviewer fills in the three missing amounts, with a typo in the balance.
        for name in ["total_billed", "adjustments"]:
            f = fields.get(name=name)
            self.client.post(
                f"/api/fields/{f.id}/review/",
                {"decision": "edit", "corrected_value": self.truth[name]},
                format="json",
            )
        balance = fields.get(name="balance_due")
        body = self.client.post(
            f"/api/fields/{balance.id}/review/",
            {"decision": "edit", "corrected_value": "1.00"},
            format="json",
        ).json()
        self.assertFalse(body["is_valid"])
        self.assertIn("arithmetic", body["validation_message"])
        body = self.client.post(
            f"/api/fields/{balance.id}/review/",
            {"decision": "edit", "corrected_value": self.truth["balance_due"]},
            format="json",
        ).json()
        self.assertTrue(body["is_valid"])

    def test_edit_requires_corrected_value(self):
        doc_id = self._upload().json()["id"]
        field_id = ExtractedField.objects.filter(run__document_id=doc_id).first().id
        r = self.client.post(f"/api/fields/{field_id}/review/", {"decision": "edit"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_metrics_report_accuracy_and_flag_recall(self):
        self._upload()
        m = self.client.get("/api/metrics/").json()
        self.assertEqual(m["overall"]["documents_scored"], 1)
        self.assertLess(m["overall"]["accuracy"], 1.0)
        # Every error on this bill is a missing field, and missing fields are always flagged.
        self.assertEqual(m["overall"]["flag_recall"], 1.0)

    @override_settings(LIENLENS_EXTRACTOR="llm")
    def test_llm_path_with_fake_client(self):
        t = self.truth
        tool_input = {
            "provider_name": {"value": t["provider_name"], "confidence": 0.98},
            "provider_npi": {"value": t["provider_npi"], "confidence": 0.99},
            "patient_name": {"value": t["patient_name"], "confidence": 0.97},
            "date_of_service": {"value": t["date_of_service"], "confidence": 0.95},
            "total_billed": {"value": f"${t['total_billed']}", "confidence": 0.96},
            "adjustments": {"value": t["adjustments"], "confidence": 0.9},
            "balance_due": {"value": t["balance_due"], "confidence": 0.93},
            "line_items": t["line_items"],
        }
        fake = FakeLLMClient(tool_input)
        with open(self.path, "rb") as fh:
            doc = Document.objects.create(
                file=SimpleUploadedFile(self.path.name, fh.read()),
                original_name=self.path.name,
                ground_truth=t,
            )
        run = process_document(doc, llm_client=fake)
        self.assertEqual(run.extractor, "llm")
        self.assertEqual(fake.calls[0]["tool_choice"]["type"], "auto")
        self.assertEqual(compute_metrics()["overall"]["accuracy"], 1.0)
        self.assertFalse(run.fields.filter(needs_review=True).exists())

    def test_llm_without_tool_use_fails_cleanly(self):
        class Broken(FakeLLMClient):
            def create(self, **kwargs):
                return SimpleNamespace(content=[SimpleNamespace(type="text", text="sorry")])

        with self.assertRaises(ValueError):
            llm.extract("text", client=Broken({}))
