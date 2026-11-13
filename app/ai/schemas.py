"""LLM 출력 검증용 스키마. 파싱 후 이 모델로 검증하고, 실패하면 1회 재시도한다."""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="ignore")


class HardWordOut(_Strict):
    word: str
    meaning: str


class ImageSuggestionOut(_Strict):
    needed: bool
    reason: str = ""
    prompt: str = ""


class RestructureOut(_Strict):
    easy_sentences: list[str] = Field(min_length=1)
    hard_words: list[HardWordOut] = Field(default_factory=list)
    image_suggestion: ImageSuggestionOut


def strict_json_schema(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    """OpenAI 호환 response_format(json_schema, strict). Gateway 문서상 strict + additionalProperties:false 필수."""
    return {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}}


_HARD_WORDS = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"word": {"type": "string"}, "meaning": {"type": "string"}},
        "required": ["word", "meaning"],
        "additionalProperties": False,
    },
}

RESTRUCTURE_SCHEMA = strict_json_schema(
    "page_restructure",
    {
        "type": "object",
        "properties": {
            "easy_sentences": {"type": "array", "items": {"type": "string"}},
            "hard_words": _HARD_WORDS,
            "image_suggestion": {
                "type": "object",
                "properties": {
                    "needed": {"type": "boolean"},
                    "reason": {"type": "string"},
                    "prompt": {"type": "string"},
                },
                "required": ["needed", "reason", "prompt"],
                "additionalProperties": False,
            },
        },
        "required": ["easy_sentences", "hard_words", "image_suggestion"],
        "additionalProperties": False,
    },
)
