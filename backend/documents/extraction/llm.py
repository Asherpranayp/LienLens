"""LLM extractor using the Anthropic API with forced tool use.

Forcing the model to "call" a tool whose input schema is our field schema
gives structured JSON back instead of free text, which removes a whole class
of parsing failures. Output still goes through the same validation as the
rule-based extractor, because a well-formed answer can still be wrong.
"""

from django.conf import settings

from .base import ExtractionResult, FieldGuess

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """You extract billing data from medical bills for lien resolution.
Rules:
- Copy values exactly as they appear on the document. Do not guess or infer.
- If a field is not present, return null for it and set its confidence to 0.
- Confidence is your probability (0 to 1) that the value is correct.
- Line items are individual billed services with a CPT/HCPCS code and an amount.
- "Balance due" may be labeled e.g. "Amount You Owe", "Please Pay", or "Patient Responsibility".
- "Adjustments" may be labeled e.g. "Discount" or "Contractual Adjustment"."""

FIELD_SPEC = {
    "provider_name": "Name of the billing or rendering provider/practice",
    "provider_npi": "10-digit National Provider Identifier",
    "patient_name": "Patient's full name",
    "date_of_service": "Date the service was provided, as written",
    "total_billed": "Total charges before adjustments, as written",
    "adjustments": "Total adjustments/discounts, as written",
    "balance_due": "Amount the patient/guarantor owes, as written",
}


def _tool_schema() -> dict:
    field_props = {
        name: {
            "type": "object",
            "description": desc,
            "properties": {
                "value": {"type": ["string", "null"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["value", "confidence"],
        }
        for name, desc in FIELD_SPEC.items()
    }
    return {
        "name": "record_bill",
        "description": "Record the structured fields extracted from a medical bill.",
        "input_schema": {
            "type": "object",
            "properties": {
                **field_props,
                "line_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string"},
                            "description": {"type": "string"},
                            "amount": {"type": "string"},
                        },
                        "required": ["code", "description", "amount"],
                    },
                },
            },
            "required": [*FIELD_SPEC.keys(), "line_items"],
        },
    }


def extract(text: str, client=None) -> ExtractionResult:
    """Extract fields with an LLM. `client` can be injected for testing."""
    if client is None:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    model = settings.LIENLENS_LLM_MODEL
    response = client.messages.create(
        model=model,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        tools=[_tool_schema()],
        tool_choice={"type": "auto"},
        messages=[{"role": "user", "content": f"Call the record_bill tool with the extracted fields.\n<document>\n{text}\n</document>"}],
    )

    tool_input = next(
        (block.input for block in response.content if getattr(block, "type", "") == "tool_use"),
        None,
    )
    if tool_input is None:
        raise ValueError("LLM response did not include structured output")

    fields = {}
    for name in FIELD_SPEC:
        item = tool_input.get(name) or {}
        value = item.get("value")
        confidence = float(item.get("confidence") or 0.0)
        fields[name] = FieldGuess(value, confidence if value else 0.0)

    return ExtractionResult(
        fields=fields,
        line_items=tool_input.get("line_items") or [],
        extractor="llm",
        model_name=model,
        prompt_version=PROMPT_VERSION,
    )
