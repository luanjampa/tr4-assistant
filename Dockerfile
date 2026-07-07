FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1 \
    TR4_DATA_DIR=/data

RUN mkdir -p /data

EXPOSE 8000

CMD ["uvicorn", "tr4.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
