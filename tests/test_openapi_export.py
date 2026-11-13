from scripts.export_openapi import OUTPUT, render


def test_docs_openapi_json_is_up_to_date():
    """API를 바꾸고 docs/openapi.json을 다시 만들지 않으면 실패한다."""
    assert OUTPUT.exists(), "docs/openapi.json이 없습니다. python -m scripts.export_openapi 실행"
    assert OUTPUT.read_text(encoding="utf-8") == render(), (
        "docs/openapi.json이 최신이 아닙니다. `.venv/bin/python -m scripts.export_openapi`로 갱신하세요."
    )
