"""Generate synthetic bills and run them through the full extraction pipeline.

    python manage.py seed_demo --count 12
"""

import tempfile
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand

from documents.extraction.pipeline import choose_extractor, enqueue_extraction
from documents.models import Document
from documents.synthetic import generate


class Command(BaseCommand):
    help = "Create synthetic medical bills with ground truth and extract them."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=12)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--reset", action="store_true", help="Delete existing documents first")

    def handle(self, *args, count, seed, reset, **options):
        if reset:
            deleted, _ = Document.objects.all().delete()
            self.stdout.write(f"Deleted {deleted} existing records.")

        self.stdout.write(f"Extractor: {choose_extractor()}")
        with tempfile.TemporaryDirectory() as tmp:
            for path, truth in generate(Path(tmp), count, seed=seed):
                with open(path, "rb") as fh:
                    doc = Document.objects.create(
                        file=File(fh, name=path.name),
                        original_name=path.name,
                        ground_truth=truth,
                    )
                enqueue_extraction(doc)
                doc.refresh_from_db()
                self.stdout.write(f"  {path.name}: {doc.status}")

        self.stdout.write(self.style.SUCCESS(f"Seeded {count} synthetic bills."))
