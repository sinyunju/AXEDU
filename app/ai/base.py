"""LLM/이미지 provider 인터페이스.

모든 메서드는 CLAUDE.md 7절의 JSON 스키마에 맞는 dict를 반환한다.
"""
from abc import ABC, abstractmethod
from typing import Any


class AIProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def restructure_page(self, source_text: str) -> dict[str, Any]:
        """→ {easy_sentences: [str], hard_words: [{word, meaning}], image_suggestion: {needed, reason, prompt} | None}"""

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

    @abstractmethod
    async def generate_image(self, prompt: str) -> bytes:
        """→ PNG bytes"""
