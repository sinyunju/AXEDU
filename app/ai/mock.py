"""MOCK_AI=true 일 때 쓰는 고정 응답 provider. API 키 없이 프론트 연동용."""
from typing import Any

import pymupdf

from app.ai.base import AIProvider, ImageProvider


def _placeholder_png(prompt: str) -> bytes:
    """512x512 자리표시 이미지 (API 호출 없음)."""
    doc = pymupdf.open()
    page = doc.new_page(width=512, height=512)
    page.draw_rect(page.rect, color=None, fill=(0.93, 0.95, 0.98))
    page.draw_rect(pymupdf.Rect(16, 16, 496, 496), color=(0.6, 0.68, 0.8), width=3, dashes="[12] 0")
    page.insert_text((40, 240), "MOCK IMAGE", fontname="helv", fontsize=40, color=(0.35, 0.45, 0.6))
    page.insert_textbox(pymupdf.Rect(40, 270, 472, 470), prompt[:120], fontname="korea", fontsize=16,
                        color=(0.4, 0.45, 0.55))
    return page.get_pixmap(alpha=False).tobytes("png")


class MockProvider(AIProvider):
    name = "mock"

    async def restructure_page(self, source_text: str) -> dict[str, Any]:
        head = source_text.strip().splitlines()[0][:20] if source_text.strip() else "이 페이지"
        return {
            "easy_sentences": [f"{head}에 대해 배워요.", "중요한 내용을 하나씩 봐요.", "천천히 읽어 보세요."],
            "hard_words": [{"word": "광합성", "meaning": "식물이 햇빛으로 양분을 만드는 일"}],
            # 데모용: "과정"이 들어간 페이지에만 이미지 제안
            "image_suggestion": (
                {"needed": True, "reason": "과정의 순서를 그림으로 보면 이해가 쉬워요",
                 "prompt": "글자 없는 단순한 교육용 일러스트: " + head}
                if "과정" in source_text
                else {"needed": False, "reason": "", "prompt": ""}
            ),
        }

    async def live_caption(self, source_text: str, transcript: str, previous_easy: list[str]) -> dict[str, Any]:
        snippet = transcript.strip()[-25:] if transcript.strip() else ""
        new = [f"선생님 말씀: {snippet}"] if snippet else []
        return {"easy_transcript": [*previous_easy, *new], "hard_words": []}

    async def generate_quiz(self, pages: list[dict[str, Any]], transcripts: list[dict[str, Any]]) -> dict[str, Any]:
        first_page = pages[0]["page_no"] if pages else 1
        return {
            "questions": [
                {
                    "id": 1,
                    "type": "ox",
                    "question": "식물은 햇빛으로 양분을 만들어요.",
                    "answer": "O",
                    "explanation": "맞아요. 이것을 광합성이라고 해요.",
                    "page_no": first_page,
                },
                {
                    "id": 2,
                    "type": "choice",
                    "question": "광합성에 꼭 필요한 것은 무엇일까요?",
                    "choices": ["햇빛", "소금", "모래"],
                    "answer": "햇빛",
                    "explanation": "식물은 햇빛이 있어야 양분을 만들어요.",
                    "page_no": first_page,
                },
            ]
        }

    async def chat(
        self, pages: list[dict[str, Any]], transcripts: list[dict[str, Any]], history: list[dict[str, str]], message: str
    ) -> dict[str, Any]:
        related = pages[0]["page_no"] if pages else None
        return {"answer": "좋은 질문이에요. 교과서 내용을 다시 볼까요?", "related_page": related}


class MockImageProvider(ImageProvider):
    name = "mock"

    async def generate_image(self, prompt: str) -> bytes:
        return _placeholder_png(prompt)
