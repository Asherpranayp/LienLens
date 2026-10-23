from dataclasses import dataclass, field


@dataclass
class FieldGuess:
    value: str | None
    confidence: float


@dataclass
class ExtractionResult:
    fields: dict[str, FieldGuess]
    line_items: list[dict] = field(default_factory=list)
    extractor: str = "rules"
    model_name: str = ""
    prompt_version: str = ""
