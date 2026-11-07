"""Coda dei job su Postgres (Procrastinate).

Il worker si connette con lo stesso ruolo dell'API e quindi rispetta la RLS:
ogni job riceve il workspace_id e lega la sessione a quel workspace.

Code:
- `ingest`: controlli leggeri sui file caricati (worker standard);
- `docs`: estrazione del testo da documenti (con OCR) e pagine web (worker standard);
- `index`: embeddings per la ricerca, calcolati dall'embedder interno (worker standard);
- `stt`: trascrizione e diarization, pesante (worker dedicato, una alla volta);
- `llm`: elaborazioni con il modello linguistico (worker standard).
"""

import io
import logging
import tempfile
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from procrastinate import App, PsycopgConnector, RetryStrategy
from procrastinate.exceptions import AlreadyEnqueued
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import llm, storage
from app.config import get_settings
from app.db import SessionLocal, bind_workspace
from app.models import (
    Asset,
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
QUEUE_DOCS = "docs"
QUEUE_INDEX = "index"
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
        elif source.type == SourceType.document:
            source.status_detail = "In coda per l'estrazione del testo"
            db.commit()
            extract_document.defer(workspace_id=workspace_id, source_id=source_id)
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
            # Se il riconoscimento delle voci fallisce, la trascrizione resta valida (una voce sola)
            try:
                turns = diarize.diarize(
                    samples, audio.SAMPLE_RATE, progress.phase("Riconoscimento delle voci", stt_end, 0.98)
                )
            except Exception as exc:
                log.exception("Riconoscimento delle voci fallito durante la trascrizione")
                transcript.diarize_status = JobStatus.failed
                transcript.diarize_error = (
                    str(exc)
                    if isinstance(exc, diarize.DiarizationUnavailable)
                    else "Riconoscimento delle voci non riuscito"
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
    queue_index(source)


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

    profile = llm.route(llm.Task.clean, [source.confidentiality])
    if profile is None:
        raise llm.LlmUnavailable(llm.unavailable_reason([source.confidentiality]))
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


# --- Testo di documenti, pagine web e note -------------------------------------------


def save_text_version(
    db: Session,
    source: Source,
    *,
    engine: str,
    paragraphs: list,
    model: str = "-",
    user_id: uuid.UUID | None = None,
) -> Transcript:
    """Salva il testo estratto come nuova versione corrente (pronta subito)."""
    db.execute(
        update(Transcript)
        .where(Transcript.source_id == source.id, Transcript.is_current)
        .values(is_current=False)
    )
    db.flush()
    t = Transcript(
        workspace_id=source.workspace_id,
        source_id=source.id,
        is_current=True,
        status=JobStatus.ready,
        progress=1.0,
        engine=engine,
        model=model,
        created_by=user_id,
        completed_at=_now(),
    )
    db.add(t)
    db.flush()
    db.add_all(
        Segment(
            workspace_id=source.workspace_id,
            transcript_id=t.id,
            idx=i,
            page=p.page,
            text_raw=p.text,
            words=[],
        )
        for i, p in enumerate(paragraphs)
    )
    return t


def _fail(db: Session, workspace_id: str, source_id: str, detail: str) -> None:
    db.rollback()
    bind_workspace(db, uuid.UUID(workspace_id))
    source = db.get(Source, uuid.UUID(source_id))
    if source is not None:
        source.status = SourceStatus.failed
        source.status_detail = detail[:500]
        db.commit()


def run_extract_document(db: Session, source: Source) -> None:
    from app.pipeline.documents import extract

    original = next((a for a in source.assets if a.kind == AssetKind.original), None)
    if original is None:
        raise RuntimeError("File originale mancante")
    source.status_detail = "Estrazione del testo in corso"
    db.commit()
    with tempfile.TemporaryDirectory(prefix="doc-") as tmp:
        result = extract(_download_original(source, Path(tmp)), original.mime_type)
    save_text_version(db, source, engine=result.engine, paragraphs=result.paragraphs)
    meta = dict(source.meta or {})
    if result.pages:
        meta["pages"] = result.pages
    if result.ocr_pages:
        meta["ocr_pages"] = result.ocr_pages
    source.meta = meta
    source.status = SourceStatus.ready
    source.status_detail = None if result.paragraphs else "Nessun testo trovato nel documento"
    db.commit()
    queue_index(source)


@app.task(name="sources.extract_document", queue=QUEUE_DOCS, retry=RetryStrategy(max_attempts=2))
def extract_document(workspace_id: str, source_id: str) -> None:
    from app.pipeline.documents import ExtractionError

    with SessionLocal() as db:
        bind_workspace(db, uuid.UUID(workspace_id))
        source = db.get(Source, uuid.UUID(source_id))
        if source is None:
            return
        try:
            run_extract_document(db, source)
        except ExtractionError as exc:
            _fail(db, workspace_id, source_id, str(exc))
        except Exception:
            log.exception("Estrazione fallita per la fonte %s", source_id)
            _fail(db, workspace_id, source_id, "Errore durante l'estrazione del testo")


def run_fetch_web(db: Session, source: Source) -> None:
    from app.pipeline import documents, web

    source.status = SourceStatus.processing
    source.status_detail = "Scaricamento della pagina"
    db.commit()
    fetched = web.fetch(source.url or "")
    meta = dict(source.meta or {})
    meta.update(
        final_url=fetched.url,
        fetched_at=fetched.fetched_at.isoformat(),
        http_status=fetched.status,
        redirects=fetched.redirects,
    )

    is_pdf = fetched.content_type == web.PDF_TYPE
    asset_id = uuid.uuid4()
    key = storage.object_key(source.workspace_id, source.id, asset_id)
    stored = storage.put(
        key,
        io.BytesIO(fetched.body),
        fetched.content_type,
        max_bytes=get_settings().web_max_bytes,
    )
    db.add(
        Asset(
            id=asset_id,
            workspace_id=source.workspace_id,
            source_id=source.id,
            # Il PDF scaricato è l'originale; per l'HTML si conserva la copia della pagina
            kind=AssetKind.original if is_pdf else AssetKind.derived,
            storage_key=key,
            filename="documento.pdf" if is_pdf else "copia-della-pagina.html",
            mime_type=fetched.content_type,
            size_bytes=stored.size,
            sha256=stored.sha256,
        )
    )

    if is_pdf:
        with tempfile.TemporaryDirectory(prefix="web-") as tmp:
            path = Path(tmp) / "doc.pdf"
            path.write_bytes(fetched.body)
            result = documents.extract_pdf(path)
        paragraphs, engine = result.paragraphs, f"web+{result.engine}"
        if result.pages:
            meta["pages"] = result.pages
    else:
        article = web.extract_article(fetched.body, fetched.url)
        paragraphs = documents.web_text_to_paragraphs(article.text)
        engine = "web"
        meta.update(site=article.site, author=article.author, published=article.date)
        if article.title and source.meta.get("auto_title"):
            source.title = article.title[:300]
        if article.date and source.source_date is None:
            try:
                source.source_date = datetime.fromisoformat(article.date[:10]).date()
            except ValueError:
                pass
    meta.pop("auto_title", None)
    source.meta = meta
    save_text_version(db, source, engine=engine, paragraphs=paragraphs)
    source.status = SourceStatus.ready
    source.status_detail = None if paragraphs else "Nessun testo riconosciuto nella pagina"
    db.commit()
    queue_index(source)


@app.task(name="sources.fetch_web", queue=QUEUE_DOCS)
def fetch_web(workspace_id: str, source_id: str) -> None:
    from app.pipeline.documents import ExtractionError
    from app.pipeline.web import FetchError

    with SessionLocal() as db:
        bind_workspace(db, uuid.UUID(workspace_id))
        source = db.get(Source, uuid.UUID(source_id))
        if source is None:
            return
        try:
            run_fetch_web(db, source)
        except (FetchError, ExtractionError) as exc:
            _fail(db, workspace_id, source_id, str(exc))
        except Exception:
            log.exception("Acquisizione della pagina fallita per la fonte %s", source_id)
            _fail(db, workspace_id, source_id, "Errore durante l'acquisizione della pagina")


# --- Indice per la ricerca ------------------------------------------------------------


def queue_index(source: Source) -> None:
    """Mette in coda il calcolo degli embeddings (un solo job in attesa per fonte)."""
    try:
        index_source.configure(queueing_lock=f"index:{source.id}").defer(
            workspace_id=str(source.workspace_id), source_id=str(source.id)
        )
    except AlreadyEnqueued:
        pass


def run_index(db: Session, source: Source, embed=None) -> int:
    """Calcola gli embeddings mancanti dei segmenti della versione corrente."""
    from app import embeddings

    embed = embed or embeddings.embed
    t = db.scalar(select(Transcript).where(Transcript.source_id == source.id, Transcript.is_current))
    if t is None:
        return 0
    todo = db.scalars(
        select(Segment)
        .where(Segment.transcript_id == t.id, Segment.embedding.is_(None))
        .order_by(Segment.idx)
    ).all()
    done = 0
    for i in range(0, len(todo), 32):
        batch = todo[i : i + 32]
        # Contesto minimo: il titolo della fonte aiuta a distinguere passaggi simili
        texts = [f"{source.title}\n{s.text_edited or s.text_raw}" for s in batch]
        for seg, vector in zip(batch, embed(texts), strict=True):
            seg.embedding = vector
        db.commit()
        done += len(batch)
    return done


@app.task(
    name="sources.index",
    queue=QUEUE_INDEX,
    retry=RetryStrategy(max_attempts=5, exponential_wait=10),
)
def index_source(workspace_id: str, source_id: str) -> None:
    with SessionLocal() as db:
        bind_workspace(db, uuid.UUID(workspace_id))
        source = db.get(Source, uuid.UUID(source_id))
        if source is None:
            return
        run_index(db, source)


# --- Riconoscimento delle voci su una trascrizione esistente --------------------------


def _load_samples(source: Source):
    """Audio dell'originale come PCM 16 kHz mono (separato per poterlo sostituire nei test)."""
    from app.pipeline import audio

    with tempfile.TemporaryDirectory(prefix="diar-") as tmp:
        src = _download_original(source, Path(tmp))
        return audio.load_pcm(audio.normalize(src, Path(tmp) / "audio.wav"))


def run_rediarize(db: Session, source: Source, transcript: Transcript) -> None:
    """Assegna gli interlocutori ai passaggi senza ritrascrivere.

    - Correzioni, versione pulita e testo restano.
    - Un passaggio non corretto in cui parlano più persone viene diviso nei turni.
    - Un passaggio corretto (le parole non corrispondono più ai tempi) va a chi
      parla per più tempo al suo interno.
    - Gli interlocutori precedenti vengono sostituiti da "Voce 1", "Voce 2"...
    """
    from app.pipeline import audio, diarize
    from app.pipeline.segmentation import assign_speakers, build_segments

    transcript.diarize_status = JobStatus.processing
    transcript.diarize_error = None
    db.commit()

    samples = _load_samples(source)
    turns = diarize.diarize(samples, audio.SAMPLE_RATE, lambda _p: None)
    if not turns:
        raise RuntimeError("Nessuna voce riconosciuta nell'audio")

    old = db.scalars(
        select(Segment).where(Segment.transcript_id == transcript.id).order_by(Segment.idx)
    ).all()
    plan: list[
        tuple[Segment | None, object, str | None]
    ] = []  # (segmento esistente o None, pezzo, etichetta)
    for seg in old:
        if seg.words and seg.text_edited is None:
            pieces = build_segments(seg.words, turns, target_seconds=0.0, max_seconds=30.0)
            if len(pieces) > 1:
                plan.extend((None, piece, piece.speaker) for piece in pieces)
                continue
            label = pieces[0].speaker if pieces else None
        else:
            # Chi parla per più tempo nell'intervallo del passaggio
            span = [["", seg.start or 0.0, seg.end or 0.0, 1.0]]
            label = assign_speakers(span, turns)[0]
        plan.append((seg, None, label))

    # Interlocutori nell'ordine in cui parlano per la prima volta
    speakers: dict[str | None, Speaker] = {}
    for _, _, label in plan:
        if label not in speakers:
            speakers[label] = Speaker(
                workspace_id=transcript.workspace_id,
                transcript_id=transcript.id,
                label=f"Voce {len(speakers) + 1}",
            )
    db.add_all(speakers.values())
    db.flush()

    # Rinumerazione in due passi per non violare l'unicità (transcript_id, idx)
    kept = {id(seg) for seg, _, _ in plan if seg is not None}
    for seg in old:
        if id(seg) not in kept:
            db.delete(seg)
    db.flush()
    for i, (seg, _, _) in enumerate(plan):
        if seg is not None:
            seg.idx = -(i + 1)
    db.flush()
    for i, (seg, piece, label) in enumerate(plan):
        if seg is not None:
            seg.idx = i
            seg.speaker_id = speakers[label].id
        else:
            db.add(
                Segment(
                    workspace_id=transcript.workspace_id,
                    transcript_id=transcript.id,
                    idx=i,
                    start=piece.start,
                    end=piece.end,
                    speaker_id=speakers[label].id,
                    text_raw=piece.text,
                    words=piece.words,
                )
            )
    db.flush()
    new_ids = {sp.id for sp in speakers.values()}
    for sp in db.scalars(select(Speaker).where(Speaker.transcript_id == transcript.id)).all():
        if sp.id not in new_ids:
            db.delete(sp)
    transcript.diarized = True
    transcript.diarize_status = JobStatus.ready
    db.commit()
    queue_index(source)  # i passaggi divisi vanno indicizzati


@app.task(name="transcripts.diarize", queue=QUEUE_STT)
def rediarize_transcript(workspace_id: str, source_id: str, transcript_id: str) -> None:
    with SessionLocal() as db:
        bind_workspace(db, uuid.UUID(workspace_id))
        source = db.get(Source, uuid.UUID(source_id))
        transcript = db.get(Transcript, uuid.UUID(transcript_id))
        if source is None or transcript is None:
            return
        try:
            run_rediarize(db, source, transcript)
        except Exception as exc:
            db.rollback()
            log.exception("Riconoscimento delle voci fallito per la trascrizione %s", transcript_id)
            transcript = db.get(Transcript, uuid.UUID(transcript_id))
            if transcript is None:
                return
            from app.pipeline.diarize import DiarizationUnavailable

            transcript.diarize_status = JobStatus.failed
            transcript.diarize_error = (
                str(exc)
                if isinstance(exc, DiarizationUnavailable | RuntimeError)
                else "Errore durante il riconoscimento delle voci"
            )
            db.commit()
