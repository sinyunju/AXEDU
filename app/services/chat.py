"""챗봇 답변 후처리: 4분류(CLAUDE.md 7절 작업 4) 규칙을 모델 출력과 관계없이 서버에서 보장한다."""
from typing import Any

from app.ai.prompts import NOT_COVERED_ANSWER, OFF_TOPIC_ANSWER


def finalize_chat(result: dict[str, Any], valid_pages: set[int]) -> tuple[str, int | None]:
    """→ (저장·반환할 답변, related_page)

    - basic(기초 질문)은 근거 페이지가 반드시 있어야 한다. 없거나 유효하지 않으면 not_covered(심화)로 바꾼다.
    - not_covered / off_topic은 정해진 문구로 통일한다.
    - 유효하지 않은 페이지 번호는 None.
    """
    kind = str(result.get("kind") or "lesson")
    answer = str(result.get("answer", "")).strip()
    page = result.get("related_page")
    page = page if page in valid_pages else None

    if kind == "basic" and page is None:
        kind = "not_covered"
    if kind == "not_covered":
        return NOT_COVERED_ANSWER, page
    if kind == "off_topic":
        return OFF_TOPIC_ANSWER, None
    if kind == "care":
        return answer, None
    return answer, page
