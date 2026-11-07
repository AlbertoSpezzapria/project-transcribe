"""Servizio interno degli embeddings (rete Docker interna, nessuna porta esposta).

Un solo processo tiene il modello in memoria e serve sia l'indicizzazione
(worker) sia le query (API). Il testo non lascia il server.

Avvio: uvicorn app.embedder:app --port 8001
"""

import logging
import threading

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings
from app.models import EMBEDDING_DIM

log = logging.getLogger(__name__)
app = FastAPI(title="Redazione embedder", docs_url=None, redoc_url=None, openapi_url=None)

_model = None
_lock = threading.Lock()


def _load():
    global _model
    with _lock:
        if _model is None:
            import torch
            from sentence_transformers import SentenceTransformer

            device = "cuda" if torch.cuda.is_available() else "cpu"
            name = get_settings().embedding_model
            log.info("Carico il modello di embeddings %s su %s", name, device)
            _model = SentenceTransformer(name, device=device)
            if _model.get_embedding_dimension() != EMBEDDING_DIM:
                raise RuntimeError(f"Il modello deve produrre vettori di dimensione {EMBEDDING_DIM}")
    return _model


@app.on_event("startup")
def _warmup() -> None:
    # Caricamento in background: il primo download del modello può richiedere minuti
    threading.Thread(target=_load, daemon=True).start()


class EmbedRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=256)


class EmbedResponse(BaseModel):
    vectors: list[list[float]]


@app.get("/health")
def health():
    return {"ready": _model is not None}


@app.post("/embed", response_model=EmbedResponse)
def embed(body: EmbedRequest):
    try:
        model = _load()
    except Exception as exc:  # modello non scaricabile, memoria, ...
        log.exception("Embedder non disponibile")
        raise HTTPException(503, "Modello di embeddings non disponibile") from exc
    texts = [t[:8000] for t in body.texts]
    vectors = model.encode(texts, batch_size=16, normalize_embeddings=True, convert_to_numpy=True)
    return EmbedResponse(vectors=[[round(float(x), 6) for x in v] for v in vectors])
