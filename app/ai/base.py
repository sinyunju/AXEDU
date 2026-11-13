"""LLM/이미지 provider 인터페이스.

텍스트(MOCK_AI)와 이미지(MOCK_IMAGE)는 따로 mock 처리할 수 있도록 provider를 분리한다.
모든 텍스트 메서드는 CLAUDE.md 7절의 JSON 스키마에 맞는 dict를 반환한다.
"""
from abc import ABC, abstractmethod
from typing import Any


def image_extension(data: bytes) -> str | None:
    """매직 바이트로 이미지 확장자 판별. 이미지가 아니면 None."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


class AIError(RuntimeError):
    """AI 호출 실패 (네트워크, 응답 형식 오류, 재시도 후에도 JSON 파싱 실패 등)."""


class AIProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def restructure_page(self, source_text: str) -> dict[str, Any]:
        """→ {easy_sentences: [str], hard_words: [{word, meaning}], image_suggestion: {needed, reason, prompt}}"""

    @abstractmethod
    async def live_caption(
        self, source_text: str, transcript: str, previous_easy: list[str]
    ) -> dict[str, Any]:
        """→ {easy_transcript: [str], hard_words: [{word, meaning}]}"""

    @abstractmethod
    async def generate_quiz(self, pages: list[dict[str, Any]], transcripts: list[dict[str, Any]]) -> dict[str, Any]:
        """→ {questions: [{id, type: "ox"|"choice", question, choices?, answer, explanation, page_no}]}"""

    @abstractmethod
    async def chat(
        self, pages: list[dict[str, Any]], transcripts: list[dict[str, Any]], history: list[dict[str, str]], message: str
    ) -> dict[str, Any]:
        """→ {answer: str, related_page: int | None}"""


class ImageProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def generate_image(self, prompt: str) -> bytes:
        """→ 이미지 bytes (PNG/JPEG 등)"""
