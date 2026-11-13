from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    database_url: str = "sqlite:///./easyclass.db"
    storage_dir: Path = Path("./storage")
    # 쉼표 구분 문자열. 예: "http://localhost:3000,https://xxx.vercel.app"
    frontend_origins: str = "http://localhost:3000,http://localhost:5173"

    # PDF 업로드
    max_upload_mb: int = 30
    max_pdf_pages: int = 100
    pdf_render_zoom: float = 1.5  # 72dpi 기준 배율 (1.5 → 108dpi)

    jwt_secret: str = "change-me"
    jwt_expire_minutes: int = 720

    mock_ai: bool = True
    ai_base_url: str = "https://api.baze.co/v1/gateway"
    ai_api_key: str = ""
    model_fast: str = "gemini-3.5-flash-lite"
    model_main: str = "gemini-3.8-flash"
    model_image: str = "gemini-nano-banana-2.1"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.frontend_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
