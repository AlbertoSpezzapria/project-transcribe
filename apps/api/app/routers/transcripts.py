"""Trascrizioni: lettura, correzione dei segmenti, interlocutori, versioni, export."""

import uuid
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select, update

from app import jobs, llm
from app.audit import audit
from app.deps import WorkspaceContext, workspace_context
from app.models import JobStatus, Segment, Source, SourceType, Speaker, Transcript
from app.pipeline import diarize
from app.routers.sources import _get_source
from app.schemas import (
    SegmentOut,
    SegmentUpdate,
    SpeakerCreate,
    SpeakerMerge,
    SpeakerOut,
    SpeakerUpdate,
    TranscribeRequest,
    TranscriptOut,
    TranscriptSummary,
)

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["transcripts"])

_BUSY = (JobStatus.queued, JobStatus.processing)


def _get_transcript(ctx: WorkspaceContext, transcript_id: uuid.UUID) -> Transcript:
    t = ctx.db.scalar(
        select(Transcript).where(Transcript.id == transcript_id, Transcript.workspace_id == ctx.workspace_id)
    )
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trascrizione non trovata")
    return t


def _get_speaker(ctx: WorkspaceContext, speaker_id: uuid.UUID) -> Speaker:
    sp = ctx.db.scalar(
        select(Speaker).where(Speaker.id == speaker_id, Speaker.workspace_id == ctx.workspace_id)
    )
    if sp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interlocutore non trovato")
    return sp


def _pending(ctx: WorkspaceContext, current: Transcript) -> Transcript | None:
    """La versione più recente non ancora corrente, se è in corso o fallita dopo quella attuale."""
    t = ctx.db.scalar(
        select(Transcript)
        .where(
            Transcript.source_id == current.source_id,
            Transcript.is_current.is_(False),
            Transcript.created_at > current.created_at,
        )
        .order_by(Transcript.created_at.desc())
        .limit(1)
    )
    return t if t is not None and t.status != JobStatus.ready else None


def _transcript_out(ctx: WorkspaceContext, source: Source, t: Transcript) -> TranscriptOut:
    speakers = ctx.db.scalars(
        select(Speaker).where(Speaker.transcript_id == t.id).order_by(Speaker.created_at, Speaker.label)
    ).all()
    segments = ctx.db.scalars(
        select(Segment).where(Segment.transcript_id == t.id).order_by(Segment.idx)
    ).all()
    pending = _pending(ctx, t)
    profile = llm.route(llm.Task.clean, [source.confidentiality])
    return TranscriptOut(
        **TranscriptSummary.model_validate(t).model_dump(),
        peaks=t.peaks,
        speakers=[SpeakerOut.model_validate(s) for s in speakers],
        segments=[SegmentOut.model_validate(s) for s in segments],
        pending=TranscriptSummary.model_validate(pending) if pending else None,
        clean_available=profile is not None,
        clean_unavailable_reason=None if profile else llm.unavailable_reason([source.confidentiality]),
        diarization_available=diarize.configured() and source.type in (SourceType.audio, SourceType.video),
    )


@router.get("/sources/{source_id}/transcript", response_model=TranscriptOut)
def get_transcript(source_id: uuid.UUID, ctx: WorkspaceContext = Depends(workspace_context)):
    source = _get_source(ctx, source_id)
    t = ctx.db.scalar(select(Transcript).where(Transcript.source_id == source.id, Transcript.is_current))
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nessuna trascrizione per questa fonte")
    return _transcript_out(ctx, source, t)


@router.get("/sources/{source_id}/transcripts", response_model=list[TranscriptSummary])
def list_versions(source_id: uuid.UUID, ctx: WorkspaceContext = Depends(workspace_context)):
    source = _get_source(ctx, source_id)
    return ctx.db.scalars(
        select(Transcript).where(Transcript.source_id == source.id).order_by(Transcript.created_at.desc())
    ).all()


@router.post("/sources/{source_id}/transcribe", response_model=TranscriptSummary, status_code=202)
def transcribe(
    source_id: uuid.UUID,
    body: TranscribeRequest,
    request: Request,
    ctx: WorkspaceContext = Depends(workspace_context),
):
    """Nuova trascrizione. Le correzioni della versione attuale restano nella sua versione."""
    source = _get_source(ctx, source_id)
    if source.type not in (SourceType.audio, SourceType.video):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Solo le fonti audio e video si trascrivono")
    busy = ctx.db.scalar(
        select(Transcript.id).where(Transcript.source_id == source.id, Transcript.status.in_(_BUSY))
    )
    if busy:
        raise HTTPException(status.HTTP_409_CONFLICT, "C'è già una trascrizione in corso")
    t = jobs.queue_transcription(ctx.db, source, language=body.language, user_id=ctx.user.id)
    audit(
        ctx.db,
        "transcript.requested",
        request=request,
        user_id=ctx.user.id,
        workspace_id=ctx.workspace_id,
        object_type="source",
        object_id=source.id,
    )
    ctx.db.commit()
    return TranscriptSummary.model_validate(ctx.db.get(Transcript, t.id))


@router.post("/transcripts/{transcript_id}/activate", response_model=TranscriptSummary)
def activate_version(transcript_id: uuid.UUID, ctx: WorkspaceContext = Depends(workspace_context)):
    """Torna a una versione precedente (pronta) della trascrizione."""
    t = _get_transcript(ctx, transcript_id)
    if t.status != JobStatus.ready:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Si può attivare solo una versione completata")
    ctx.db.execute(
        update(Transcript)
        .where(Transcript.source_id == t.source_id, Transcript.is_current)
        .values(is_current=False)
    )
    ctx.db.flush()
    t.is_current = True
    ctx.db.commit()
    return TranscriptSummary.model_validate(t)


# --- Segmenti ---------------------------------------------------------------------


@router.patch("/segments/{segment_id}", response_model=SegmentOut)
def update_segment(
    segment_id: uuid.UUID, body: SegmentUpdate, ctx: WorkspaceContext = Depends(workspace_context)
):
    seg = ctx.db.scalar(
        select(Segment).where(Segment.id == segment_id, Segment.workspace_id == ctx.workspace_id)
    )
    if seg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Segmento non trovato")
    data = body.model_dump(exclude_unset=True)
    reindex = False
    if "text" in data:
        text = (data["text"] or "").strip()
        # Testo uguale al verbatim (o vuoto) = nessuna correzione
        new = None if not text or text == seg.text_raw else text
        if new != seg.text_edited:
            seg.text_edited = new
            seg.text_clean = None  # la versione pulita va rigenerata per questo passaggio
            seg.embedding = None  # e l'indice per la ricerca va ricalcolato
            reindex = True
    if "speaker_id" in data:
        if data["speaker_id"] is not None:
            sp = _get_speaker(ctx, data["speaker_id"])
            if sp.transcript_id != seg.transcript_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Interlocutore di un'altra trascrizione")
        seg.speaker_id = data["speaker_id"]
    seg.edited_by = ctx.user.id
    seg.edited_at = datetime.now(UTC)
    ctx.db.commit()
    if reindex:
        t = ctx.db.get(Transcript, seg.transcript_id)
        source = ctx.db.get(Source, t.source_id) if t else None
        if source is not None and t.is_current:
            jobs.queue_index(source)
    return SegmentOut.model_validate(seg)


# --- Interlocutori -------------------------------------------------------------------


@router.post("/transcripts/{transcript_id}/speakers", response_model=SpeakerOut, status_code=201)
def create_speaker(
    transcript_id: uuid.UUID, body: SpeakerCreate, ctx: WorkspaceContext = Depends(workspace_context)
):
    t = _get_transcript(ctx, transcript_id)
    n = ctx.db.scalar(select(func.count()).where(Speaker.transcript_id == t.id)) or 0
    sp = Speaker(
        workspace_id=ctx.workspace_id, transcript_id=t.id, label=f"Voce {n + 1}", name=body.name.strip()
    )
    ctx.db.add(sp)
    ctx.db.commit()
    return SpeakerOut.model_validate(sp)


@router.patch("/speakers/{speaker_id}", response_model=SpeakerOut)
def rename_speaker(
    speaker_id: uuid.UUID, body: SpeakerUpdate, ctx: WorkspaceContext = Depends(workspace_context)
):
    sp = _get_speaker(ctx, speaker_id)
    sp.name = (body.name or "").strip() or None
    ctx.db.commit()
    return SpeakerOut.model_validate(sp)


@router.post("/speakers/{speaker_id}/merge", status_code=204)
def merge_speaker(
    speaker_id: uuid.UUID, body: SpeakerMerge, ctx: WorkspaceContext = Depends(workspace_context)
):
    """Unisce due interlocutori (la diarization a volte divide la stessa persona in due)."""
    sp = _get_speaker(ctx, speaker_id)
    target = _get_speaker(ctx, body.into_id)
    if target.id == sp.id or target.transcript_id != sp.transcript_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unione non valida")
    ctx.db.execute(update(Segment).where(Segment.speaker_id == sp.id).values(speaker_id=target.id))
    if not target.name and sp.name:
        target.name = sp.name
    ctx.db.delete(sp)
    ctx.db.commit()


# --- Riconoscimento delle voci ------------------------------------------------------


@router.post("/transcripts/{transcript_id}/diarize", response_model=TranscriptSummary, status_code=202)
def request_diarize(transcript_id: uuid.UUID, ctx: WorkspaceContext = Depends(workspace_context)):
    """Riconosce chi parla sulla trascrizione esistente, senza ritrascrivere."""
    t = _get_transcript(ctx, transcript_id)
    source = _get_source(ctx, t.source_id)
    if source.type not in (SourceType.audio, SourceType.video):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Solo per audio e video")
    if not diarize.configured():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Riconoscimento delle voci non configurato")
    if t.status != JobStatus.ready:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La trascrizione non è ancora pronta")
    if t.diarize_status in _BUSY:
        raise HTTPException(status.HTTP_409_CONFLICT, "Riconoscimento delle voci già in corso")
    t.diarize_status = JobStatus.queued
    t.diarize_error = None
    ctx.db.commit()
    jobs.rediarize_transcript.defer(
        workspace_id=str(ctx.workspace_id), source_id=str(source.id), transcript_id=str(t.id)
    )
    return TranscriptSummary.model_validate(t)


# --- Versione pulita ---------------------------------------------------------------


@router.post("/transcripts/{transcript_id}/clean", response_model=TranscriptSummary, status_code=202)
def request_clean(transcript_id: uuid.UUID, ctx: WorkspaceContext = Depends(workspace_context)):
    t = _get_transcript(ctx, transcript_id)
    source = _get_source(ctx, t.source_id)
    if t.status != JobStatus.ready:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La trascrizione non è ancora pronta")
    if t.clean_status in _BUSY:
        raise HTTPException(status.HTTP_409_CONFLICT, "Versione pulita già in preparazione")
    if llm.route(llm.Task.clean, [source.confidentiality]) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, llm.unavailable_reason([source.confidentiality]))
    t.clean_status = JobStatus.queued
    t.clean_error = None
    ctx.db.commit()
    jobs.clean_transcript.defer(
        workspace_id=str(ctx.workspace_id), source_id=str(source.id), transcript_id=str(t.id)
    )
    return TranscriptSummary.model_validate(t)


# --- Export ----------------------------------------------------------------------------


def _ts(seconds: float, srt: bool = False) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}" if srt else f"{h:02}:{m:02}:{s:02}"


@router.get("/transcripts/{transcript_id}/export")
def export_transcript(
    transcript_id: uuid.UUID,
    request: Request,
    format: Literal["txt", "srt"] = "txt",
    text: Literal["edited", "clean"] = "edited",
    ctx: WorkspaceContext = Depends(workspace_context),
):
    t = _get_transcript(ctx, transcript_id)
    source = _get_source(ctx, t.source_id)
    names = {
        sp.id: sp.name or sp.label
        for sp in ctx.db.scalars(select(Speaker).where(Speaker.transcript_id == t.id))
    }
    segments = ctx.db.scalars(
        select(Segment).where(Segment.transcript_id == t.id).order_by(Segment.idx)
    ).all()

    def body(s: Segment) -> str:
        verbatim = s.text_edited or s.text_raw
        return (s.text_clean or verbatim) if text == "clean" else verbatim

    is_media = source.type in (SourceType.audio, SourceType.video)
    if format == "srt" and not is_media:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "I sottotitoli esistono solo per audio e video")
    if format == "srt":
        content = "\n".join(
            f"{i}\n{_ts(s.start or 0, True)} --> {_ts(s.end or 0, True)}\n"
            f"{names.get(s.speaker_id, '') + ': ' if s.speaker_id else ''}{body(s)}\n"
            for i, s in enumerate(segments, start=1)
        )
    else:
        header = f"{source.title}\n"
        if source.source_date:
            header += f"Data: {source.source_date.isoformat()}\n"
        if text == "clean":
            header += "Versione pulita: non usare per le citazioni testuali.\n"
        if is_media:
            lines = [
                f"[{_ts(s.start or 0)}] {names.get(s.speaker_id, 'Voce') if s.speaker_id else 'Voce'}: "
                f"{body(s)}"
                for s in segments
            ]
        else:
            lines, page = [], None
            for s in segments:
                if s.page is not None and s.page != page:
                    page = s.page
                    lines.append(f"— Pagina {page} —")
                lines.append(body(s))
        if source.url:
            header += f"Indirizzo: {source.url}\n"
        content = header + "\n" + "\n\n".join(lines) + "\n"

    audit(
        ctx.db,
        "transcript.exported",
        request=request,
        user_id=ctx.user.id,
        workspace_id=ctx.workspace_id,
        object_type="transcript",
        object_id=t.id,
        format=format,
        text=text,
    )
    ctx.db.commit()
    filename = f"{source.title[:80]} - trascrizione.{format}"
    return Response(
        content,
        media_type="text/plain; charset=utf-8" if format == "txt" else "application/x-subrip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "private, no-store",
        },
    )
