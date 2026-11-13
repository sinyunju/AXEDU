"""OpenAPI 명세를 docs/openapi.json으로 내보낸다 (서버 실행 없이 API 명세를 볼 수 있게).

  .venv/bin/python -m scripts.export_openapi            # docs/openapi.json 갱신
  .venv/bin/python -m scripts.export_openapi --check    # 파일이 최신인지 확인만 (다르면 종료 코드 1)

API(라우터·스키마)를 바꾸면 다시 실행해서 함께 커밋한다. tests/test_openapi_export.py가 최신 여부를 검사한다.
"""
import argparse
import json
import sys
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / "docs" / "openapi.json"


def render() -> str:
    from app.main import create_app

    spec = create_app().openapi()
    return json.dumps(spec, ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="파일이 최신인지 확인만 한다")
    args = parser.parse_args()

    content = render()
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != content:
            sys.exit(f"{OUTPUT} 가 최신이 아닙니다. `python -m scripts.export_openapi`로 갱신하세요.")
        print("최신입니다.")
        return
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content, encoding="utf-8")
    spec = json.loads(content)
    print(f"{OUTPUT} 저장 (경로 {len(spec['paths'])}개, 스키마 {len(spec['components']['schemas'])}개)")


if __name__ == "__main__":
    main()
