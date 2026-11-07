"""Coda dei job su Postgres (Procrastinate).

Il worker si connette con lo stesso ruolo dell'API e quindi rispetta la RLS:
ogni job riceve il workspace_id e lega la sessione a quel workspace.
Avvio: `procrastinate --app=app.jobs.app worker`
"""

import logging
import uuid

from procrastinate import App, PsycopgConnector, RetryStrategy

from app import storage
from app.config import get_settings
from app.db import SessionLocal, bind_workspace
from app.models import AssetKind, Source, SourceStatus, SourceType

log = logging.getLogger(__name__)


def _conninfo() -> str:
    return get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")


app = App(connector=PsycopgConnector(conninfo=_conninfo()))

QUEUE_INGEST = "ingest"


@app.task(
    name="sources.ingest",
    queue=QUEUE_INGEST,
    retry=RetryStrategy(max_attempts=3, exponential_wait=5),
)
def ingest_source(workspace_id: str, source_id: str) -> None:
    """Fase 1: verifica l'integrità dell'originale e segna la fonte come pronta.

    Le fasi successive aggiungono qui i passi della pipeline (normalizzazione,
    trascrizione, diarization, arricchimento, indicizzazione), ognuno come job a sé.
    """
    with SessionLocal() as db:
        bind_workspace(db, uuid.UUID(workspace_id))
        source = db.get(Source, uuid.UUID(source_id))
        if source is None:
            log.warning("Fonte %s non trovata (cancellata?)", source_id)
            return
        source.status = SourceStatus.processing
        db.commit()
        try:
            originals = [a for a in source.assets if a.kind == AssetKind.original]
            for asset in originals:
                meta = storage.head(asset.storage_key)
                if int(meta["ContentLength"]) != asset.size_bytes:
                    raise RuntimeError("Dimensione del file nello storage non corrispondente")
            source.status = SourceStatus.ready
            source.status_detail = (
                "In attesa della trascrizione (disponibile dalla Fase 2)"
                if source.type in (SourceType.audio, SourceType.video)
                else None
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            source.status = SourceStatus.failed
            source.status_detail = "Errore durante l'elaborazione del file"
            db.commit()
            log.exception("Ingestione fallita per la fonte %s", source_id)
            raise exc
