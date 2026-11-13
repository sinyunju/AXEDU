"""PDF → 페이지별 텍스트 + PNG 렌더링 (PyMuPDF)."""
import uuid
from dataclasses import dataclass
from pathlib import Path

import pymupdf

PAGES_SUBDIR = "pages"


class PdfError(ValueError):
    """사용자에게 보여 줄 수 있는 PDF 처리 오류."""


@dataclass
class RenderedPage:
    page_no: int  # 1부터
    image_path: str  # storage_dir 기준 상대 경로 (예: "pages/<uuid>.png")
    source_text: str


def render_pdf(data: bytes, storage_dir: Path, *, max_pages: int, zoom: float) -> list[RenderedPage]:
    """PDF를 페이지별로 렌더링해 storage_dir/pages/ 에 저장한다.

    실패하면 이미 만든 파일을 지우고 PdfError를 던진다.
    파일명은 추측하기 어렵게 UUID를 쓴다 (/files 는 인증 없이 제공되므로).
    """
    if not data.startswith(b"%PDF"):
        raise PdfError("PDF 파일만 올릴 수 있습니다")
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as e:  # pymupdf.FileDataError 등
        raise PdfError("PDF 파일을 읽을 수 없습니다") from e

    out_dir = storage_dir / PAGES_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    try:
        if doc.needs_pass:
            raise PdfError("암호가 걸린 PDF는 올릴 수 없습니다")
        if doc.page_count == 0:
            raise PdfError("페이지가 없는 PDF입니다")
        if doc.page_count > max_pages:
            raise PdfError(f"PDF는 최대 {max_pages}페이지까지 올릴 수 있습니다 (현재 {doc.page_count}페이지)")

        matrix = pymupdf.Matrix(zoom, zoom)
        pages: list[RenderedPage] = []
        for index, page in enumerate(doc):
            filename = f"{uuid.uuid4().hex}.png"
            path = out_dir / filename
            page.get_pixmap(matrix=matrix, alpha=False).save(path)
            written.append(path)
            pages.append(RenderedPage(index + 1, f"{PAGES_SUBDIR}/{filename}", page.get_text().strip()))
        return pages
    except PdfError:
        remove_files(written)
        raise
    except Exception as e:
        remove_files(written)
        raise PdfError("PDF 페이지를 처리하지 못했습니다") from e
    finally:
        doc.close()


def remove_files(paths: list[Path]) -> None:
    for p in paths:
        p.unlink(missing_ok=True)
