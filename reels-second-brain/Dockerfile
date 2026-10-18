FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV RSB_DATA_DIR=/data PYTHONUNBUFFERED=1
# 웹: uvicorn, 워커: python -m rsb.worker (같은 이미지, 실행 명령만 다르게)
CMD ["sh", "-c", "python -m rsb.cli migrate && uvicorn rsb.asgi:app --host 0.0.0.0 --port ${PORT:-8000}"]
