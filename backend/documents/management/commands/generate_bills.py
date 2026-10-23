"""Write synthetic bill PDFs (and a ground-truth JSON per bill) to a folder,
for uploading through the UI by hand.

    python manage.py generate_bills --count 6 --out sample_bills
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand

from documents.synthetic import generate


class Command(BaseCommand):
    help = "Generate synthetic medical bill PDFs with ground-truth JSON."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=6)
        parser.add_argument("--seed", type=int, default=7)
        parser.add_argument("--out", default="sample_bills")

    def handle(self, *args, count, seed, out, **options):
        out_dir = Path(out)
        for path, truth in generate(out_dir, count, seed=seed):
            path.with_suffix(".json").write_text(json.dumps(truth, indent=2))
            self.stdout.write(f"  {path}")
        self.stdout.write(self.style.SUCCESS(f"Wrote {count} bills to {out_dir}/"))
