"""퀴즈 생성 입력 구성, LLM 문항 검증·정규화, 채점."""
import logging
import random
from typing import Any


logger = logging.getLogger(__name__)

OX_CHOICES = ["O", "X"]
_OX_ALIASES = {"o": "O", "○": "O", "⭕": "O", "x": "X", "×": "X", "✕": "X", "❌": "X"}
MAX_QUESTIONS = 10


class QuizValidationError(ValueError):
    pass


def normalize_ox(value: str) -> str | None:
    v = value.strip()
    v = _OX_ALIASES.get(v.lower(), _OX_ALIASES.get(v, v.upper()))
    return v if v in OX_CHOICES else None


def normalize_questions(raw: list[dict[str, Any]], valid_pages: set[int]) -> list[dict[str, Any]]:
    """규칙에 맞지 않는 문항은 버리고, 선다형 보기 순서를 섞고, id를 1부터 다시 매긴다."""
    out: list[dict[str, Any]] = []
    for q in raw:
        qtype = str(q.get("type", "")).strip().lower()
        question = str(q.get("question", "")).strip()
        explanation = str(q.get("explanation", "")).strip()
        page_no = q.get("page_no")
        if not question:
            continue
        if page_no not in valid_pages:
            page_no = None  # 근거 페이지가 틀려도 문항 자체는 살린다
        if qtype == "ox":
            answer = normalize_ox(str(q.get("answer", "")))
            if answer is None:
                logger.info("OX 문항 버림(정답 형식): %r", q)
                continue
            choices = OX_CHOICES
        elif qtype == "choice":
            choices = [str(c).strip() for c in q.get("choices", []) if str(c).strip()]
            answer = str(q.get("answer", "")).strip()
            if len(choices) != 3 or len(set(choices)) != 3 or answer not in choices:
                logger.info("선다형 문항 버림(보기/정답): %r", q)
                continue
            # LLM은 정답을 첫 보기에 두는 경향이 있어 순서를 섞는다 ("항상 1번" 찍기 방지)
            choices = random.sample(choices, k=len(choices))
        else:
            continue
        out.append({"id": len(out) + 1, "type": qtype, "question": question, "choices": list(choices),
                    "answer": answer, "explanation": explanation, "page_no": page_no})
        if len(out) >= MAX_QUESTIONS:
            break
    if not out:
        raise QuizValidationError("사용할 수 있는 문항이 없습니다")
    return out


def grade(questions: list[dict[str, Any]], answers: dict[int, str]) -> tuple[int, list[dict[str, Any]]]:
    """answers: {question_id: 학생 답}. 답하지 않은 문항은 오답. → (점수, 문항별 결과)"""
    results = []
    score = 0
    for q in questions:
        given = answers.get(q["id"])
        if given is not None and q["type"] == "ox":
            given = normalize_ox(given) or given.strip()
        elif given is not None:
            given = given.strip()
        correct = given is not None and given == q["answer"]
        score += int(correct)
        results.append({"question_id": q["id"], "answer": given, "correct": correct,
                        "correct_answer": q["answer"], "explanation": q["explanation"], "page_no": q["page_no"]})
    return score, results


def check_answers(questions: list[dict[str, Any]], answers: list[tuple[int, str]]) -> dict[int, str]:
    """형식 검사: 없는 문항·중복·보기에 없는 답이면 QuizValidationError."""
    by_id = {q["id"]: q for q in questions}
    result: dict[int, str] = {}
    for qid, ans in answers:
        q = by_id.get(qid)
        if q is None:
            raise QuizValidationError(f"{qid}번 문항이 없습니다")
        if qid in result:
            raise QuizValidationError(f"{qid}번 문항의 답이 두 번 있습니다")
        valid = (normalize_ox(ans) is not None) if q["type"] == "ox" else ans.strip() in q["choices"]
        if not valid:
            raise QuizValidationError(f"{qid}번 문항의 답은 보기 중 하나여야 합니다: {q['choices']}")
        result[qid] = ans
    return result
