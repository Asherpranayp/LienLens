"""Synthetic medical bill generator.

Produces PDF bills in three different layouts, plus the ground truth for each,
so extraction accuracy can be measured. All names and numbers are fake.
Layouts deliberately vary labels, date formats, and ordering, which is what
makes real-world bills hard to extract.
"""

import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

PROVIDERS = [
    "North Texas Orthopedic Associates",
    "Lakeside Imaging Center",
    "Prairie Physical Therapy Group",
    "Trinity Emergency Physicians",
    "Cedar Ridge Neurology Clinic",
    "Elm Street Chiropractic",
    "Riverbend Surgical Partners",
    "Summit Pain Management",
]

FIRST_NAMES = ["Jordan", "Taylor", "Morgan", "Casey", "Riley", "Avery", "Quinn", "Parker"]
LAST_NAMES = ["Alvarez", "Brooks", "Chen", "Delgado", "Ellison", "Fischer", "Grant", "Hayes"]

PROCEDURES = [
    ("99213", "Office visit, established patient"),
    ("99283", "Emergency department visit"),
    ("72110", "X-ray, lumbar spine, 4 views"),
    ("72148", "MRI lumbar spine without contrast"),
    ("97110", "Therapeutic exercise, 15 min"),
    ("97140", "Manual therapy, 15 min"),
    ("98941", "Chiropractic manipulation, 3-4 regions"),
    ("20610", "Joint injection, major joint"),
    ("64483", "Epidural steroid injection, lumbar"),
    ("J1030", "Methylprednisolone acetate, 40 mg"),
]


def _npi_check_digit(first9: str) -> str:
    """NPI check digit: Luhn over the 80840 prefix + first 9 digits."""
    digits = "80840" + first9
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:  # double every other digit, starting from the rightmost
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def make_npi(rng: random.Random) -> str:
    first9 = "1" + "".join(str(rng.randint(0, 9)) for _ in range(8))
    return first9 + _npi_check_digit(first9)


@dataclass
class Bill:
    provider_name: str
    provider_npi: str
    patient_name: str
    date_of_service: date
    line_items: list = field(default_factory=list)  # (code, description, Decimal)
    adjustments: Decimal = Decimal("0.00")
    layout: str = "A"

    @property
    def total_billed(self) -> Decimal:
        return sum((amt for _, _, amt in self.line_items), Decimal("0.00"))

    @property
    def balance_due(self) -> Decimal:
        return self.total_billed - self.adjustments

    def ground_truth(self) -> dict:
        return {
            "provider_name": self.provider_name,
            "provider_npi": self.provider_npi,
            "patient_name": self.patient_name,
            "date_of_service": self.date_of_service.isoformat(),
            "total_billed": f"{self.total_billed:.2f}",
            "adjustments": f"{self.adjustments:.2f}",
            "balance_due": f"{self.balance_due:.2f}",
            "line_items": [
                {"code": c, "description": d, "amount": f"{a:.2f}"} for c, d, a in self.line_items
            ],
            "layout": self.layout,
        }


def random_bill(rng: random.Random, layout: str) -> Bill:
    items = rng.sample(PROCEDURES, rng.randint(2, 5))
    line_items = [
        (code, desc, Decimal(rng.randint(85, 2400)) + Decimal(rng.choice([0, 0.5, 0.25])))
        for code, desc in items
    ]
    bill = Bill(
        provider_name=rng.choice(PROVIDERS),
        provider_npi=make_npi(rng),
        patient_name=f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
        date_of_service=date(2026, 1, 1) + timedelta(days=rng.randint(0, 250)),
        line_items=line_items,
        layout=layout,
    )
    total = bill.total_billed
    bill.adjustments = (total * Decimal(rng.choice(["0", "0.1", "0.2", "0.35"]))).quantize(
        Decimal("0.01")
    )
    return bill


def _money(v: Decimal) -> str:
    return f"${v:,.2f}"


def render_pdf(bill: Bill, path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=letter)
    w, h = letter
    c.setTitle("Synthetic medical bill (LienLens demo)")
    y = h - 60

    def line(text, x=50, size=10, bold=False, dy=16):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(x, y, text)
        y -= dy

    if bill.layout == "A":
        # Classic itemized statement: provider header, labeled fields, table.
        line(bill.provider_name, size=16, bold=True, dy=20)
        line("1200 Main Street, Denton, TX 76201", dy=14)
        line(f"NPI: {bill.provider_npi}", dy=28)
        line("ITEMIZED STATEMENT", size=12, bold=True, dy=22)
        line(f"Patient: {bill.patient_name}")
        line(f"Date of Service: {bill.date_of_service.strftime('%m/%d/%Y')}", dy=26)
        line("CPT     Description                                   Charge", bold=True)
        for code, desc, amt in bill.line_items:
            c.setFont("Helvetica", 10)
            c.drawString(50, y, code)
            c.drawString(105, y, desc)
            c.drawRightString(520, y, _money(amt))
            y -= 16
        y -= 10
        for label, val in [
            ("Total Charges", bill.total_billed),
            ("Adjustments", bill.adjustments),
            ("Balance Due", bill.balance_due),
        ]:
            c.setFont("Helvetica-Bold", 10)
            c.drawString(330, y, f"{label}:")
            c.drawRightString(520, y, _money(val))
            y -= 16

    elif bill.layout == "B":
        # Hospital-style: statement title first, different labels and date format.
        line("PATIENT ACCOUNT STATEMENT", size=14, bold=True, dy=22)
        line(f"Billing Provider: {bill.provider_name}")
        line(f"Provider NPI #{bill.provider_npi}", dy=24)
        line(f"Guarantor / Patient Name: {bill.patient_name}")
        line(f"Service Date: {bill.date_of_service.strftime('%B %d, %Y')}", dy=26)
        line("Code    Service Description                         Amount", bold=True)
        for code, desc, amt in bill.line_items:
            c.setFont("Helvetica", 10)
            c.drawString(50, y, code)
            c.drawString(105, y, desc)
            c.drawRightString(520, y, _money(amt))
            y -= 16
        y -= 10
        for label, val in [
            ("Total Billed", bill.total_billed),
            ("Insurance/Contractual Adjustment", bill.adjustments),
            ("Amount You Owe", bill.balance_due),
        ]:
            c.setFont("Helvetica-Bold", 10)
            c.drawString(250, y, f"{label}:")
            c.drawRightString(520, y, _money(val))
            y -= 16

    else:
        # Clinic invoice: totals summary at the top, ISO dates, terse labels.
        line("INVOICE", size=18, bold=True, dy=24)
        line(bill.provider_name, size=12, bold=True)
        line(f"Rendering NPI {bill.provider_npi}", dy=24)
        line(f"Amount Billed {_money(bill.total_billed)}")
        line(f"Discount {_money(bill.adjustments)}")
        line(f"Please Pay {_money(bill.balance_due)}", bold=True, dy=26)
        line(f"Patient {bill.patient_name}")
        line(f"DOS {bill.date_of_service.isoformat()}", dy=26)
        line("Item    Description                                  Fee", bold=True)
        for code, desc, amt in bill.line_items:
            c.setFont("Helvetica", 10)
            c.drawString(50, y, code)
            c.drawString(105, y, desc)
            c.drawRightString(520, y, _money(amt))
            y -= 16

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(50, 40, "SYNTHETIC DOCUMENT - generated for LienLens demo. Contains no real PHI.")
    c.showPage()
    c.save()


def generate(out_dir: Path, count: int, seed: int = 42) -> list[tuple[Path, dict]]:
    """Generate `count` bills cycling through layouts A, B, C."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    results = []
    for i in range(count):
        layout = "ABC"[i % 3]
        bill = random_bill(rng, layout)
        path = out_dir / f"bill_{i + 1:03d}_layout{layout}.pdf"
        render_pdf(bill, path)
        results.append((path, bill.ground_truth()))
    return results
