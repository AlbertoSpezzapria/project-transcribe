"""Coda dei job su Postgres (Procrastinate).

Il worker si connette con lo stesso ruolo dell'API e quindi rispetta la RLS:
ogni job riceve il workspace_id e lega la sessione a quel workspace.

Code:
- `ingest`: controlli leggeri sui file caricati (worker standard);
- `stt`: trascrizione e diarization, pesante (worker dedicato, una alla volta);
- `llm`: elaborazioni con il modello linguistico (worker standard).
"""

import logging
import tempfile
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from procrastinate import App, PsycopgConnector, RetryStrategy
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import llm, storage
from app.config import get_settings
from app.db import SessionLocal, bind_workspace
from app.models import (
    AssetKind,
    JobStatus,
    Segment,
    Source,
    SourceStatus,
    SourceType,
    Speaker,
    Transcript,
)

log = logging.getLogger(__name__)


def _conninfo() -> str:
    return get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")


app = App(connector=PsycopgConnector(conninfo=_conninfo()))

QUEUE_INGEST = "ingest"
QUEUE_STT = "stt"
QUEUE_LLM = "llm"


def _now() -> datetime:
    return datetime.now(UTC)


# --- Avvio della trascrizione (usato dall'ingestione e dall'API) -----------------


def queue_transcription(
    db: Session, source: Source, *, language: str | None, user_id: uuid.UUID | None
) -> Transcript:
    """Crea una nuova versione della trascrizione e la mette in coda.

    Se esiste già una versione corrente, la nuova diventa corrente solo quando è pronta:
    nel frattempo si continua a vedere (e correggere) quella precedente.
    """
    from app.pipeline.stt import get_engine

    engine = get_engine()
    current = db.scalar(select(Transcript).where(Transcript.source_id == source.id, Transcript.is_current))
    # Una versione corrente fallita non ha nulla da mostrare: la nuova la sostituisce subito.
    if current is not None and current.status == JobStatus.failed:
        current.is_current = False
        db.flush()
        current = None
    transcript = Transcript(
        workspace_id=source.workspace_id,
        source_id=source.id,
        is_current=current is None,
        status=JobStatus.queued,
        engine=engine.name,
        model=engine.model,
        language=language,
        created_by=user_id,
    )
    db.add(transcript)
    source.status = SourceStatus.processing
    source.status_detail = "In coda per la trascrizione"
    db.flush()
    transcript_id = transcript.id
    db.commit()
    transcribe_source.defer(
        workspace_id=str(source.workspace_id), source_id=str(source.id), transcript_id=str(transcript_id)
    )
    return transcript


@app.task(
    name="sources.ingest",
    queue=QUEUE_INGEST,
    retry=RetryStrategy(max_attempts=3, exponential_wait=5),
)
def ingest_source(workspace_id: str, source_id: str) -> None:
    """Verifica l'integrità dell'originale; per audio e video avvia la trascrizione."""
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
        except Exception:
            db.rollback()
            source.status = SourceStatus.failed
            source.status_detail = "Errore durante l'elaborazione del file"
            db.commit()
            log.exception("Ingestione fallita per la fonte %s", source_id)
            raise
        if source.type in (SourceType.audio, SourceType.video):
            queue_transcription(
                db, source, language=get_settings().stt_default_language, user_id=source.created_by
            )
        else:
            source.status = SourceStatus.ready
            source.status_detail = None
            db.commit()


# --- Trascrizione -------------------------------------------------------------------


class _Progress:
    """Scrive l'avanzamento nel database al massimo ogni pochi secondi."""

    def __init__(self, db: Session, transcript: Transcript, source: Source, every: float = 3.0):
        self.db, self.transcript, self.source, self.every = db, transcript, source, every
        self._last = 0.0

    def phase(self, label: str, lo: float, hi: float) -> Callable[[float], None]:
        def report(p: float) -> None:
            now = time.monotonic()
            if now - self._last < self.every and p < 1.0:
                return
            self._last = now
            value = lo + (hi - lo) * max(0.0, min(p, 1.0))
            self.transcript.progress = round(value, 3)
            self.source.status_detail = f"{label} {round(value * 100)}%"
            self.db.commit()

        return report


def _download_original(source: Source, dest: Path) -> Path:
    original = next((a for a in source.assets if a.kind == AssetKind.original), None)
    if original is None:
        raise RuntimeError("File originale mancante")
    path = dest / "original"
    body = storage.get(original.storage_key)["Body"]
    with path.open("wb") as f:
        for chunk in body.iter_chunks(storage.CHUNK):
            f.write(chunk)
    return path


def run_transcription(db: Session, source: Source, transcript: Transcript) -> None:
    """Il lavoro vero e proprio, separato dal job per poterlo testare."""
    from app.pipeline import audio, diarize
    from app.pipeline.segmentation import build_segments
    from app.pipeline.stt import get_engine

    engine = get_engine()
    use_diarization = diarize.available()
    progress = _Progress(db, transcript, source)
    transcript.status = JobStatus.processing
    transcript.progress = 0.0
    transcript.error = None
    source.status_detail = "Trascrizione in corso"
    db.commit()

    with tempfile.TemporaryDirectory(prefix="stt-") as tmp:
        src = _download_original(source, Path(tmp))
        samples = None
        if engine.needs_wav:
            wav = audio.normalize(src, Path(tmp) / "audio.wav")
            samples = audio.load_pcm(wav)
            transcript.peaks = audio.peaks(samples)
            db.commit()
        else:
            wav = src

        stt_end = 0.7 if use_diarization else 0.98
        result = engine.transcribe(
            wav, samples, transcript.language, progress.phase("Trascrizione", 0.0, stt_end)
        )

        turns = []
        if use_diarization and samples is not None and result.words:
            turns = diarize.diarize(
                samples, audio.SAMPLE_RATE, progress.phase("Riconoscimento delle voci", stt_end, 0.98)
            )

    # Senza diarization ogni frase è un passaggio a sé, così il giornalista
    # può assegnare a mano ogni battuta all'interlocutore giusto.
    built = (
        build_segments(result.words, turns)
        if turns
        else build_segments(result.words, target_seconds=0.0, max_seconds=30.0)
    )

    # Gli speaker prendono il nome nell'ordine in cui parlano per la prima volta.
    speakers: dict[str | None, Speaker] = {}
    for seg in built:
        key = seg.speaker if turns else None
        if key not in speakers:
            speakers[key] = Speaker(
                workspace_id=transcript.workspace_id,
                transcript_id=transcript.id,
                label=f"Voce {len(speakers) + 1}",
            )
    db.add_all(speakers.values())
    db.flush()
    db.add_all(
        Segment(
            workspace_id=transcript.workspace_id,
            transcript_id=transcript.id,
            idx=i,
            start=seg.start,
            end=seg.end,
            speaker_id=speakers[seg.speaker if turns else None].id,
            text_raw=seg.text,
            words=seg.words,
        )
        for i, seg in enumerate(built)
    )

    transcript.detected_language = result.language
    transcript.duration = result.duration
    transcript.diarized = bool(turns)
    transcript.status = JobStatus.ready
    transcript.progress = 1.0
    transcript.completed_at = _now()
    if not transcript.is_current:
        db.execute(
            update(Transcript)
            .where(Transcript.source_id == source.id, Transcript.is_current)
            .values(is_current=False)
        )
        db.flush()
        transcript.is_current = True
    source.status = SourceStatus.ready
    source.status_detail = None if built else "Nessun parlato riconosciuto nel file"
    db.commit()


@app.task(name="sources.transcribe", queue=QUEUE_STT)
def transcribe_source(workspace_id: str, source_id: str, transcript_id: str) -> None:
    with SessionLocal() as db:
        bind_workspace(db, uuid.UUID(workspace_id))
        source = db.get(Source, uuid.UUID(source_id))
        transcript = db.get(Transcript, uuid.UUID(transcript_id))
        if source is None or transcript is None:
            log.warning("Trascrizione %s: fonte o versione non più presente", transcript_id)
            return
        try:
            run_transcription(db, source, transcript)
        except Exception as exc:
            db.rollback()
            log.exception("Trascrizione fallita per la fonte %s", source_id)
            source = db.get(Source, uuid.UUID(source_id))
            transcript = db.get(Transcript, uuid.UUID(transcript_id))
            if source is None or transcript is None:
                return
            from app.pipeline.audio import AudioError

            transcript.status = JobStatus.failed
            transcript.error = str(exc) if isinstance(exc, AudioError) else "Errore durante la trascrizione"
            # Se c'è già una versione buona, la fonte resta utilizzabile.
            has_ready = db.scalar(
                select(Transcript.id).where(
                    Transcript.source_id == source.id,
                    Transcript.is_current,
                    Transcript.status == JobStatus.ready,
                )
            )
            source.status = SourceStatus.ready if has_ready else SourceStatus.failed
            source.status_detail = None if has_ready else "Trascrizione non riuscita"
            db.commit()


# --- Versione pulita --------------------------------------------------------------


def run_clean(db: Session, source: Source, transcript: Transcript) -> None:
    from app.pipeline.clean import CleanInput, clean_segments

    profile = llm.profile_for(source.confidentiality)
    if profile is None:
        raise llm.LlmUnavailable(llm.unavailable_reason(source.confidentiality))
    transcript.clean_status = JobStatus.processing
    transcript.clean_model = f"{profile.name}:{profile.model}"
    transcript.clean_error = None
    db.commit()

    segments = db.scalars(
        select(Segment).where(Segment.transcript_id == transcript.id).order_by(Segment.idx)
    ).all()
    items = [CleanInput(idx=s.idx, text=s.text_edited or s.text_raw) for s in segments]
    accepted, rejected = clean_segments(profile, items)
    for s in segments:
        s.text_clean = accepted.get(s.idx)
    transcript.clean_status = JobStatus.ready
    transcript.clean_error = (
        f"{rejected} passaggi lasciati in versione originale dal controllo automatico" if rejected else None
    )
    db.commit()


@app.task(name="transcripts.clean", queue=QUEUE_LLM)
def clean_transcript(workspace_id: str, source_id: str, transcript_id: str) -> None:
    with SessionLocal() as db:
        bind_workspace(db, uuid.UUID(workspace_id))
        source = db.get(Source, uuid.UUID(source_id))
        transcript = db.get(Transcript, uuid.UUID(transcript_id))
        if source is None or transcript is None:
            return
        try:
            run_clean(db, source, transcript)
        except Exception as exc:
            db.rollback()
            log.exception("Versione pulita non riuscita per la trascrizione %s", transcript_id)
            transcript = db.get(Transcript, uuid.UUID(transcript_id))
            if transcript is None:
                return
            transcript.clean_status = JobStatus.failed
            transcript.clean_error = (
                str(exc) if isinstance(exc, llm.LlmUnavailable | llm.LlmError) else "Errore imprevisto"
            )
            db.commit()
