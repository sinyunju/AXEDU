from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, col, select

from app.ai import AIError, AIProvider, get_ai_provider
from app.config import get_settings
from app.db import get_session
from app.deps import require_student
from app.models import ChatMessage, ChatRole, User
from app.permissions import get_accessible_lesson
from app.schemas import ChatExchange, ChatMessageOut, ChatRequest
from app.services.chat import finalize_chat
from app.services.content import lesson_content

router = APIRouter(tags=["chat"])


def _out(m: ChatMessage) -> ChatMessageOut:
    return ChatMessageOut(id=m.id, role=m.role, content=m.content, related_page=m.related_page,
                          created_at=m.created_at)


def _my_messages(lesson_id: int, student_id: int):
    return select(ChatMessage).where(ChatMessage.lesson_id == lesson_id, ChatMessage.student_id == student_id)


@router.post(
    "/lessons/{lesson_id}/chat",
    response_model=ChatExchange,
    summary="챗봇에게 질문 (학생)",
    description="이 회차의 승인된 페이지 내용과 교사 발화를 근거로 답한다. 수업 주제와 바로 이어지는 기초 질문은 "
                "교과서 수준의 기본 지식으로 답하되 근거 페이지(related_page)를 반드시 붙이고(못 찾으면 심화로 처리), 수업에서 다루지 않은 심화 내용은 \"오늘 수업에서는 거기까지 "
                "나오지 않았어요…\", 무관한 질문은 \"이건 오늘 수업과 다른 이야기예요…\"로 안내한다. "
                "이 학생의 최근 대화(CHAT_HISTORY_LIMIT개)를 문맥으로 쓴다.",
    responses={502: {"description": "AI 호출 실패 (질문도 저장하지 않음)"}},
)
async def ask(
    lesson_id: int, body: ChatRequest,
    session: Session = Depends(get_session), student: User = Depends(require_student),
    provider: AIProvider = Depends(get_ai_provider),
) -> ChatExchange:
    lesson = get_accessible_lesson(session, lesson_id, student)
    pages, transcripts = lesson_content(session, lesson.id)

    recent = session.exec(
        _my_messages(lesson.id, student.id)
        .order_by(col(ChatMessage.id).desc()).limit(get_settings().chat_history_limit)
    ).all()
    history = [{"role": m.role, "content": m.content} for m in reversed(recent)]

    try:
        result = await provider.chat(pages, transcripts, history, body.message)
    except AIError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "지금은 답할 수 없어요. 잠시 후 다시 물어봐 주세요")

    content, related = finalize_chat(result, {p["page_no"] for p in pages})
    # 답변까지 받은 뒤 질문·답변을 함께 저장 (실패한 질문이 기록에 남지 않게)
    question = ChatMessage(lesson_id=lesson.id, student_id=student.id, role=ChatRole.user, content=body.message)
    answer = ChatMessage(lesson_id=lesson.id, student_id=student.id, role=ChatRole.assistant,
                         content=content, related_page=related)
    session.add(question)
    session.flush()  # 질문이 먼저 id를 받도록 (대화 순서)
    session.add(answer)
    session.commit()
    session.refresh(question)
    session.refresh(answer)
    return ChatExchange(question=_out(question), answer=_out(answer))


@router.get("/lessons/{lesson_id}/chat", response_model=list[ChatMessageOut],
            summary="내 챗봇 대화 기록 (학생, 오래된 것부터)")
def my_chat(
    lesson_id: int, session: Session = Depends(get_session), student: User = Depends(require_student),
) -> list[ChatMessageOut]:
    lesson = get_accessible_lesson(session, lesson_id, student)
    messages = session.exec(_my_messages(lesson.id, student.id).order_by(ChatMessage.id)).all()
    return [_out(m) for m in messages]
