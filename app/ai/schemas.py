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


CAPTION_TYPES = ("content", "flow", "notice")


class CaptionItemOut(_Strict):
    text: str
    type: str = "content"  # 알 수 없는 값은 normalize_captions()에서 content로


class LiveCaptionOut(_Strict):
    easy_transcript: list[CaptionItemOut] = Field(default_factory=list)
    hard_words: list[HardWordOut] = Field(default_factory=list)


LIVE_CAPTION_SCHEMA = strict_json_schema(
    "live_caption",
    {
        "type": "object",
        "properties": {
            "easy_transcript": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "type": {"type": "string", "enum": list(CAPTION_TYPES)},
                    },
                    "required": ["text", "type"],
                    "additionalProperties": False,
                },
            },
            "hard_words": _HARD_WORDS,
        },
        "required": ["easy_transcript", "hard_words"],
        "additionalProperties": False,
    },
)


class QuizQuestionRaw(_Strict):
    """LLM이 만든 문항 (검증·정규화 전). 의미 검증은 app/services/quiz.py에서."""

    type: str
    question: str
    choices: list[str] = Field(default_factory=list)
    answer: str
    explanation: str = ""
    page_no: int | None = None


class QuizOutRaw(_Strict):
    questions: list[QuizQuestionRaw] = Field(min_length=1)


QUIZ_SCHEMA = strict_json_schema(
    "lesson_quiz",
    {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["ox", "choice"]},
                        "question": {"type": "string"},
                        "choices": {"type": "array", "items": {"type": "string"}},
                        "answer": {"type": "string"},
                        "explanation": {"type": "string"},
                        "page_no": {"type": "integer"},
                    },
                    "required": ["type", "question", "choices", "answer", "explanation", "page_no"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["questions"],
        "additionalProperties": False,
    },
)


CHAT_KINDS = ("lesson", "basic", "not_covered", "off_topic", "care")


class ChatOut(_Strict):
    kind: str = "lesson"  # 알 수 없는 값은 서비스(finalize_chat)에서 처리
    answer: str = Field(min_length=1)
    related_page: int | None = None  # 0이면 없음 → None


CHAT_SCHEMA = strict_json_schema(
    "lesson_chat",
    {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": list(CHAT_KINDS)},
            "answer": {"type": "string"},
            "related_page": {"type": "integer"},
        },
        "required": ["kind", "answer", "related_page"],
        "additionalProperties": False,
    },
)


class TermOut(_Strict):
    meaning: str = Field(min_length=1)


TERM_SCHEMA = strict_json_schema(
    "term_meaning",
    {
        "type": "object",
        "properties": {"meaning": {"type": "string"}},
        "required": ["meaning"],
        "additionalProperties": False,
    },
)
