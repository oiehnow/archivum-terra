# 무료 CPU 호스팅용 (Render / Koyeb / Fly 등).
# 빌드 컨텍스트는 저장소 루트다.
#
# 질의 임베딩을 HF Inference API 에 맡겨 torch 와 임베딩 모델이 이미지에 들어가지 않는다.
# 실측 메모리 226MB 로 512MB 무료 티어에 들어간다.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    EMBED_BACKEND=api \
    INDEX_DIR=/app/index \
    QUOTA_DB=/tmp/quota.sqlite3 \
    HF_HOME=/tmp/.hf \
    PORT=7860

WORKDIR /app

COPY space/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 인덱스를 이미지에 굽는다.
# 무료 티어는 유휴 시 컨테이너를 재우고 깨울 때 다시 띄우는데,
# 그때마다 200MB 를 내려받으면 첫 방문자가 오래 기다린다.
# repo 가 public 이라 빌드에 토큰이 필요 없다.
RUN python -c "\
from huggingface_hub import snapshot_download; \
snapshot_download('oiehnow/wh40k-lore-index', repo_type='dataset', local_dir='/app/index')" \
    && rm -rf /tmp/.hf

COPY wh40k /app/wh40k
COPY space /app/space

RUN useradd -m -u 1000 user && chown -R user /app
USER user

EXPOSE 7860
CMD ["sh", "-c", "uvicorn space.app:app --host 0.0.0.0 --port ${PORT}"]
