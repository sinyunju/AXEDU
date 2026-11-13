"""storage_dir 아래 파일 저장/삭제. DB에는 storage_dir 기준 상대 경로를 저장한다."""
import uuid

from app.config import get_settings

GENERATED_SUBDIR = "generated"


def save_file(subdir: str, data: bytes, ext: str) -> str:
    """UUID 파일명으로 저장하고 상대 경로를 반환 (/files 는 인증 없이 제공되므로 추측 불가하게)."""
    directory = get_settings().storage_dir / subdir
    directory.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    (directory / name).write_bytes(data)
    return f"{subdir}/{name}"


def delete_file(rel_path: str | None) -> None:
    if not rel_path:
        return
    root = get_settings().storage_dir.resolve()
    path = (root / rel_path).resolve()
    if path.is_relative_to(root):  # 경로 조작 방지
        path.unlink(missing_ok=True)
