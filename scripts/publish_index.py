"""완성된 인덱스를 HF Dataset repo 에 올린다.

Space 는 시작할 때 여기서 인덱스를 내려받는다. 인덱스를 이미지에 넣지 않으므로
로어를 갱신해도 Space 를 다시 빌드할 필요가 없다.

    python scripts/publish_index.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "data" / "index"


def load_env() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    load_env()

    if not (INDEX / "meta.json").exists():
        raise SystemExit("인덱스가 없습니다. 먼저 scripts/build_index.py 를 실행하세요.")

    token = os.getenv("HF_TOKEN")
    if not token:
        raise SystemExit(
            "HF_TOKEN 이 없습니다.\n"
            "https://huggingface.co/settings/tokens 에서 write 권한 토큰을 발급해\n"
            ".env 의 HF_TOKEN 에 넣어주세요. (S3 자격증명과는 다른 값입니다)"
        )

    repo_id = os.getenv("HF_INDEX_REPO", "oiehnow/wh40k-lore-index")

    from huggingface_hub import HfApi

    api = HfApi(token=token)
    # public 으로 둔다. 자료가 CC BY-SA 공개 위키에서 온 것이라 공개해도 문제가 없고,
    # public 이면 Space 가 토큰 없이 내려받을 수 있어 배포물에 비밀을 두지 않아도 된다.
    api.create_repo(repo_id=repo_id, repo_type="dataset", private=False, exist_ok=True)

    size = sum(f.stat().st_size for f in INDEX.rglob("*") if f.is_file())
    print(f"업로드: {INDEX} ({size/1e6:.0f} MB) → {repo_id}")

    api.upload_folder(
        folder_path=str(INDEX),
        repo_id=repo_id,
        repo_type="dataset",
        commit_message="Update lore index",
    )
    print(f"완료: https://huggingface.co/datasets/{repo_id}")


if __name__ == "__main__":
    main()
