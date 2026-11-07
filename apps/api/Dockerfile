# Immagine base: API e worker leggero
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dipendenze prima del codice, per sfruttare la cache dei layer
COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py \
    && pip install -e ".[dev]" \
    && rm -rf app

RUN useradd --create-home --uid 1000 redazione

FROM base AS api
COPY . .
USER redazione
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Worker di trascrizione: ffmpeg + faster-whisper (+ pyannote se WITH_DIARIZATION=1).
# Su GPU usare una base CUDA (vedi docs/DESIGN.md §12); i modelli finiscono nel volume della cache.
FROM base AS stt
ARG WITH_DIARIZATION=0
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir app && touch app/__init__.py \
    && pip install -e ".[stt]" \
    && if [ "$WITH_DIARIZATION" = "1" ]; then \
         pip install --extra-index-url https://download.pytorch.org/whl/cpu -e ".[diarization]"; \
       fi \
    && rm -rf app
COPY . .
RUN mkdir -p /home/redazione/.cache && chown -R redazione /home/redazione/.cache
USER redazione
CMD ["procrastinate", "--app=app.jobs.app", "worker", "--queues=stt", "--concurrency=1"]
