FROM python:3.11-slim

WORKDIR /app

# System deps for faiss / pypdf wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

ENV LOG_LEVEL=INFO \
    INGESTION_INDEX_PATH=/data/vectorstore

VOLUME ["/data"]

ENTRYPOINT ["python", "-m", "src.ingestion.pipeline"]
