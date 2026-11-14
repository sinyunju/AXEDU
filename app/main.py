import logging
import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.ai import get_ai_provider, get_image_provider
from app.config import get_settings
from app.db import init_db
from app.routers import annotations, auth, chat, courses, lessons, quiz, ws
from app.services.generation import recover_stuck_generations
from app.services.live import LiveHub

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: str
    mock_ai: bool
    mock_image: bool
    ai_provider: str
    image_provider: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 설정 오류(MOCK_AI=false인데 키 없음 등)는 첫 요청이 아니라 시작 시점에 드러나게
    text, image = get_ai_provider(), get_image_provider()
    logger.info("AI provider: text=%s image=%s", text.name, image.name)
    init_db()
    if recovered := recover_stuck_generations():
        logger.warning("중단된 재구성 작업 %d건을 ready로 복구", recovered)
    ticker = asyncio.create_task(app.state.live.captioner.run_ticker())
    try:
        yield
    finally:
        ticker.cancel()
        with suppress(asyncio.CancelledError):
            await ticker


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="쉬운수업 API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router)
    app.include_router(courses.router)
    app.include_router(lessons.router)
    app.include_router(quiz.router)
    app.include_router(chat.router)
    app.include_router(annotations.router)
    app.include_router(ws.router)
    # 실시간 수업 상태 (단일 프로세스 전제, app/services/live.py 참고)
    app.state.live = LiveHub(interval=settings.live_caption_interval_seconds)
    app.mount("/files", StaticFiles(directory=settings.storage_dir), name="files")

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok", mock_ai=settings.mock_ai, mock_image=settings.mock_image,
            ai_provider=get_ai_provider().name, image_provider=get_image_provider().name,
        )

    return app


app = create_app()
