"""HF Space 에 서비스를 배포한다.

배포물에는 비밀을 담지 않는다.
- LLM 키: 없음 (답변 생성은 브라우저가 Puter 로 직접 한다)
- 인덱스 토큰: 없음 (인덱스 Dataset repo 가 public 이라 익명으로 받아진다)
- OAuth 시크릿: 없음 (Puter 로그인)

따라서 Space Secrets 에 넣을 값이 하나도 없고, 노출될 키도 없다.

    python scripts/deploy_space.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPACE_DIR = ROOT / "space"
WH40K_DIR = ROOT / "wh40k"

SPACE_ID = os.getenv("HF_SPACE_REPO", "oiehnow/archivum-terra")


def load_env() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def assert_no_secrets() -> None:
    """배포 대상에 시크릿이 섞여 들어가지 않았는지 확인한다."""
    import re

    patterns = re.compile(
        r"hf_[A-Za-z0-9]{30,}|HFAK[A-Za-z0-9]{20,}|AIza[A-Za-z0-9_-]{30,}|GOCSPX-"
    )
    for directory in (SPACE_DIR, WH40K_DIR):
        for path in directory.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if patterns.search(text):
                raise SystemExit(f"배포 중단: {path} 에 시크릿으로 보이는 문자열이 있습니다")
    print("시크릿 검사 통과 — 배포물에 비밀 없음")


def main() -> None:
    load_env()

    token = os.getenv("HF_TOKEN")
    if not token:
        raise SystemExit("HF_TOKEN 이 없습니다 (.env 확인)")

    assert_no_secrets()

    from huggingface_hub import HfApi

    api = HfApi(token=token)
    api.create_repo(
        repo_id=SPACE_ID,
        repo_type="space",
        space_sdk="docker",
        private=False,
        exist_ok=True,
    )
    print(f"Space 준비됨: {SPACE_ID}")

    # space/ 내용을 루트로 올린다 (Dockerfile 과 README 가 최상단에 있어야 한다)
    api.upload_folder(
        folder_path=str(SPACE_DIR),
        repo_id=SPACE_ID,
        repo_type="space",
        ignore_patterns=["__pycache__/*", "*.pyc"],
        commit_message="Deploy Archivum Terra",
    )
    # 공용 로직은 wh40k/ 하위에 그대로 둔다 (Dockerfile 이 COPY 로 참조)
    api.upload_folder(
        folder_path=str(WH40K_DIR),
        path_in_repo="wh40k",
        repo_id=SPACE_ID,
        repo_type="space",
        ignore_patterns=["__pycache__/*", "*.pyc"],
        commit_message="Deploy shared logic",
    )

    print(f"\n배포 완료: https://huggingface.co/spaces/{SPACE_ID}")
    print(f"서비스 URL: https://{SPACE_ID.replace('/', '-').lower()}.hf.space")
    print("\n빌드에 몇 분 걸립니다 (임베딩 모델을 이미지에 굽는 단계 포함).")


if __name__ == "__main__":
    main()
