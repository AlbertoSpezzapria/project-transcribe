# Immagine base: API e worker leggero
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# OCR per i documenti scansionati (italiano e inglese)
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-ita \
    && rm -rf /var/lib/apt/lists/*

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

# Immagine dei modelli: trascrizione (ffmpeg + faster-whisper, + pyannote se
# WITH_DIARIZATION=1) ed embedder per la ricerca (torch + sentence-transformers).
# Su GPU usare una base CUDA e TORCH_INDEX adatto (vedi docs/DESIGN.md §12);
# i modelli finiscono nel volume della cache.
FROM base AS stt
ARG WITH_DIARIZATION=0
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir app && touch app/__init__.py \
    && pip install --extra-index-url "$TORCH_INDEX" -e ".[stt,embed]" \
    && if [ "$WITH_DIARIZATION" = "1" ]; then \
         pip install --extra-index-url "$TORCH_INDEX" -e ".[diarization]"; \
       fi \
    && rm -rf app
COPY . .
RUN mkdir -p /home/redazione/.cache && chown -R redazione /home/redazione/.cache
USER redazione
CMD ["procrastinate", "--app=app.jobs.app", "worker", "--queues=stt", "--concurrency=1"]
