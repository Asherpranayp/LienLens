# LienLens

**LLM-powered document extraction for medical bills, with human-in-the-loop review and per-field accuracy scoring.**

LienLens turns unstructured medical bills into structured, reviewable data. A document is uploaded, an LLM extracts key billing fields, and a reviewer confirms or corrects each field in a side-by-side review UI. Every extraction is scored field by field, so model quality is measured rather than assumed.

> **Data notice:** LienLens uses **synthetic medical bills only**. No real PHI is stored or processed. The design still follows PHI-safe practices (access control, encrypted storage, minimal logging of document contents) so it reflects how a production system handling sensitive health data should behave.

---

## Why

In personal injury settlements, medical bills and lien correspondence must be reviewed to determine what is owed and to whom. That work is largely manual: staff read inconsistent documents from many providers and re-key the same fields. LienLens explores how LLM extraction plus human review can speed this up without sacrificing accuracy.

## Features

- **Document upload**: PDF and image medical bills, stored in S3
- **Asynchronous extraction**: uploads enqueue a job on SQS; a worker runs LLM extraction so the API stays responsive
- **Structured field extraction**:
  - Provider name and NPI
  - Patient name (synthetic)
  - Dates of service
  - Line items (CPT/HCPCS code, description, billed amount)
  - Total billed, adjustments, balance due
- **Human review UI**: document on the left, extracted fields on the right; reviewers accept, edit, or flag each field
- **Per-field accuracy scoring**: extractions are compared against ground truth for synthetic documents and against reviewer corrections, producing accuracy by field and by document
- **Failure analysis**: tracks which fields and document layouts the model gets wrong most often (missing values, hallucinated values, format errors)

## Architecture

```
React / TypeScript UI
        │  REST
        ▼
Django REST Framework API ──► PostgreSQL (documents, fields, reviews, scores)
        │
        ├──► S3 (document storage)
        │
        └──► SQS (extraction jobs) ──► Extraction worker (Python + LLM)
                                              │
                                              └──► writes fields + confidence to PostgreSQL
```

| Layer | Technology |
|---|---|
| Frontend | React, TypeScript |
| Backend API | Python, Django REST Framework |
| Database | PostgreSQL |
| Storage | AWS S3 |
| Queueing | AWS SQS |
| Extraction | LLM with structured-output prompting and schema validation |
| Infrastructure | Docker, docker-compose (local) |

## How extraction works

1. A user uploads a bill and the API stores it in S3, creating a `Document` record with status `queued`.
2. The API publishes an extraction job to SQS.
3. The worker pulls the job, extracts text from the document, and prompts the LLM to return fields matching a strict JSON schema.
4. Output is validated: schema checks, type and format checks (dates, currency, CPT code patterns), and arithmetic checks (line items sum to the total).
5. Fields that fail validation or have low confidence are flagged for human review.
6. Reviewer corrections are saved and feed accuracy scoring.

## Accuracy scoring

For each field, LienLens records:

- **Exact match**, for codes, dates, and amounts
- **Normalized match**, for names and descriptions (case, whitespace, and punctuation normalized)
- **Error type**: missing, hallucinated, wrong value, or format error

Results roll up into per-field and per-document accuracy, so prompt or model changes can be compared run over run.

## Data model (core)

- `Document`: file location, status, uploaded_by, timestamps
- `ExtractionRun`: model and prompt version, latency, status
- `ExtractedField`: field name, value, confidence, validation result
- `Review`: reviewer, corrected value, decision (accept / edit / flag)
- `FieldScore`: match type, error type, score

## Security practices

- Role-based access control on documents and reviews
- S3 server-side encryption; no document contents written to application logs
- Synthetic data only; the pipeline is designed so real PHI could be handled under HIPAA-style controls

## Project status

Active development. This repository is being built out incrementally; see the roadmap below.

## Roadmap

- [ ] Django REST API: document, extraction, and review endpoints
- [ ] SQS-backed extraction worker
- [ ] React review UI with side-by-side document viewer
- [ ] Synthetic medical bill generator with ground-truth labels
- [ ] Accuracy scoring dashboard
- [ ] docker-compose for one-command local setup
- [ ] Lien correspondence extraction (letters from lienholders)

## Local setup

Setup instructions will be added alongside the docker-compose configuration.

## Author

**Asher Pranay Palle** · [github.com/Asherpranayp](https://github.com/Asherpranayp)
