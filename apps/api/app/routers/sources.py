import re
import uuid
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import jobs, storage
from app.audit import audit
from app.config import get_settings
from app.deps import WorkspaceContext, workspace_context
from app.filetypes import UnsupportedFile, detect
from app.models import (
    Asset,
    AssetKind,
    Confidentiality,
    Source,
    SourceStatus,
    SourceType,
    Story,
    StorySource,
)
from app.schemas import AssetOut, NoteCreate, SourceOut, SourceUpdate, WebCreate

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["sources"])

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def source_out(ctx: WorkspaceContext, source: Source) -> SourceOut:
    out = SourceOut.model_validate(source)
    out.assets = [AssetOut.model_validate(a) for a in source.assets]
    out.story_ids = list(
        ctx.db.scalars(select(StorySource.story_id).where(StorySource.source_id == source.id))
    )
    return out


def _get_source(ctx: WorkspaceContext, source_id: uuid.UUID) -> Source:
    source = ctx.db.scalar(
        select(Source).where(Source.id == source_id, Source.workspace_id == ctx.workspace_id)
    )
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fonte non trovata")
    return source


def _check_story(db: Session, story_id: uuid.UUID | None) -> None:
    if story_id is not None and db.get(Story, story_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Storia non trovata")


@router.get("/sources", response_model=list[SourceOut])
def list_sources(
    type: SourceType | None = None,
    story_id: uuid.UUID | None = None,
    ctx: WorkspaceContext = Depends(workspace_context),
):
    q = select(Source).where(Source.workspace_id == ctx.workspace_id)
    if type is not None:
        q = q.where(Source.type == type)
    if story_id is not None:
        q = q.join(StorySource, StorySource.source_id == Source.id).where(StorySource.story_id == story_id)
    sources = ctx.db.scalars(q.order_by(Source.created_at.desc()).limit(500)).all()
    return [source_out(ctx, s) for s in sources]


@router.post("/sources/upload", response_model=SourceOut, status_code=201)
def upload_source(
    request: Request,
    file: UploadFile = File(...),
    title: str | None = Form(default=None, max_length=300),
    source_date: date | None = Form(default=None),
    confidentiality: Confidentiality = Form(default=Confidentiality.normal),
    story_id: uuid.UUID | None = Form(default=None),
    ctx: WorkspaceContext = Depends(workspace_context),
):
    _check_story(ctx.db, story_id)
    filename = (file.filename or "file").strip()[:300]
    head = file.file.read(8192)
    file.file.seek(0)
    try:
        detected = detect(head, filename, file.content_type)
    except UnsupportedFile as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc

    source = Source(
        workspace_id=ctx.workspace_id,
        type=detected.source_type,
        title=(title or "").strip() or filename.rsplit(".", 1)[0],
        source_date=source_date,
        confidentiality=confidentiality,
        created_by=ctx.user.id,
        meta={},
    )
    ctx.db.add(source)
    ctx.db.flush()

    asset_id = uuid.uuid4()
    key = storage.object_key(ctx.workspace_id, source.id, asset_id)
    try:
        stored = storage.put(
            key, file.file, detected.mime, max_bytes=get_settings().max_upload_mb * 1024 * 1024
        )
    except storage.FileTooLarge as exc:
        ctx.db.rollback()
        storage.delete(key)
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"Il file supera il limite di {get_settings().max_upload_mb} MB",
        ) from exc

    ctx.db.add(
        Asset(
            id=asset_id,
            workspace_id=ctx.workspace_id,
            source_id=source.id,
            kind=AssetKind.original,
            storage_key=key,
            filename=filename,
            mime_type=detected.mime,
            size_bytes=stored.size,
            sha256=stored.sha256,
        )
    )
    if story_id is not None:
        ctx.db.add(StorySource(workspace_id=ctx.workspace_id, story_id=story_id, source_id=source.id))
    audit(
        ctx.db,
        "source.uploaded",
        request=request,
        user_id=ctx.user.id,
        workspace_id=ctx.workspace_id,
        object_type="source",
        object_id=source.id,
        size=stored.size,
        mime=detected.mime,
    )
    ctx.db.commit()

    jobs.ingest_source.defer(workspace_id=str(ctx.workspace_id), source_id=str(source.id))
    ctx.db.refresh(source)
    return source_out(ctx, source)


@router.post("/sources/note", response_model=SourceOut, status_code=201)
def create_note(body: NoteCreate, request: Request, ctx: WorkspaceContext = Depends(workspace_context)):
    _check_story(ctx.db, body.story_id)
    source = Source(
        workspace_id=ctx.workspace_id,
        type=SourceType.note,
        title=body.title.strip(),
        note_text=body.text,
        source_date=body.source_date,
        confidentiality=body.confidentiality,
        created_by=ctx.user.id,
        status=SourceStatus.ready,
        meta={},
    )
    ctx.db.add(source)
    ctx.db.flush()
    if body.story_id is not None:
        ctx.db.add(StorySource(workspace_id=ctx.workspace_id, story_id=body.story_id, source_id=source.id))
    # Il testo della nota diventa subito cercabile, diviso in paragrafi
    from app.pipeline.documents import text_to_paragraphs

    jobs.save_text_version(
        ctx.db, source, engine="note", paragraphs=text_to_paragraphs(body.text), user_id=ctx.user.id
    )
    audit(
        ctx.db,
        "source.note_created",
        request=request,
        user_id=ctx.user.id,
        workspace_id=ctx.workspace_id,
        object_type="source",
        object_id=source.id,
    )
    ctx.db.commit()
    jobs.queue_index(source)
    ctx.db.refresh(source)
    return source_out(ctx, source)


@router.post("/sources/web", response_model=SourceOut, status_code=201)
def create_web(body: WebCreate, request: Request, ctx: WorkspaceContext = Depends(workspace_context)):
    """Acquisisce una pagina web: copia salvata ed estrazione del testo, in background."""
    from app.pipeline.web import FetchError, check_url

    _check_story(ctx.db, body.story_id)
    try:
        url = check_url(body.url)
    except FetchError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    title = (body.title or "").strip()
    source = Source(
        workspace_id=ctx.workspace_id,
        type=SourceType.web,
        title=title or url.split("//", 1)[-1][:300],
        url=url,
        source_date=body.source_date,
        confidentiality=body.confidentiality,
        created_by=ctx.user.id,
        status=SourceStatus.uploaded,
        status_detail="In coda per l'acquisizione",
        # Il titolo provvisorio verrà sostituito da quello della pagina
        meta={} if title else {"auto_title": True},
    )
    ctx.db.add(source)
    ctx.db.flush()
    if body.story_id is not None:
        ctx.db.add(StorySource(workspace_id=ctx.workspace_id, story_id=body.story_id, source_id=source.id))
    audit(
        ctx.db,
        "source.web_added",
        request=request,
        user_id=ctx.user.id,
        workspace_id=ctx.workspace_id,
        object_type="source",
        object_id=source.id,
    )
    ctx.db.commit()
    jobs.fetch_web.defer(workspace_id=str(ctx.workspace_id), source_id=str(source.id))
    ctx.db.refresh(source)
    return source_out(ctx, source)


@router.post("/sources/{source_id}/reprocess", response_model=SourceOut, status_code=202)
def reprocess_source(source_id: uuid.UUID, ctx: WorkspaceContext = Depends(workspace_context)):
    """Ripete l'estrazione del testo di un documento o l'acquisizione di una pagina web."""
    source = _get_source(ctx, source_id)
    if source.type not in (SourceType.document, SourceType.web):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Per audio e video si usa la nuova trascrizione")
    if source.status in (SourceStatus.uploaded, SourceStatus.processing):
        raise HTTPException(status.HTTP_409_CONFLICT, "Elaborazione già in corso")
    source.status = SourceStatus.processing
    source.status_detail = "In coda"
    ctx.db.commit()
    task = jobs.extract_document if source.type == SourceType.document else jobs.fetch_web
    task.defer(workspace_id=str(ctx.workspace_id), source_id=str(source.id))
    ctx.db.refresh(source)
    return source_out(ctx, source)


@router.get("/sources/{source_id}", response_model=SourceOut)
def get_source(source_id: uuid.UUID, ctx: WorkspaceContext = Depends(workspace_context)):
    return source_out(ctx, _get_source(ctx, source_id))


@router.patch("/sources/{source_id}", response_model=SourceOut)
def update_source(
    source_id: uuid.UUID, body: SourceUpdate, ctx: WorkspaceContext = Depends(workspace_context)
):
    source = _get_source(ctx, source_id)
    data = body.model_dump(exclude_unset=True)
    if "metadata" in data:
        source.meta = data.pop("metadata") or {}
    for field, value in data.items():
        setattr(source, field, value)
    ctx.db.commit()
    ctx.db.refresh(source)
    return source_out(ctx, source)


@router.delete("/sources/{source_id}", status_code=204)
def delete_source(source_id: uuid.UUID, request: Request, ctx: WorkspaceContext = Depends(workspace_context)):
    """Cancellazione definitiva: file nello storage, righe collegate, derivati."""
    source = _get_source(ctx, source_id)
    storage.delete_prefix(f"ws/{ctx.workspace_id}/sources/{source.id}/")
    ctx.db.delete(source)
    audit(
        ctx.db,
        "source.deleted",
        request=request,
        user_id=ctx.user.id,
        workspace_id=ctx.workspace_id,
        object_type="source",
        object_id=source_id,
    )
    ctx.db.commit()


@router.get("/assets/{asset_id}/content")
def asset_content(
    asset_id: uuid.UUID,
    request: Request,
    range_header: str | None = Header(default=None, alias="range"),
    download: bool = False,
    ctx: WorkspaceContext = Depends(workspace_context),
):
    """Scarica o riproduce un file. Supporta le richieste Range (seek nel player audio)."""
    asset = ctx.db.scalar(select(Asset).where(Asset.id == asset_id, Asset.workspace_id == ctx.workspace_id))
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File non trovato")

    size = asset.size_bytes
    start, end = 0, size - 1
    partial = False
    if range_header:
        m = _RANGE_RE.match(range_header.strip())
        if not m or (not m.group(1) and not m.group(2)):
            raise HTTPException(status.HTTP_416_RANGE_NOT_SATISFIABLE, "Range non valido")
        if m.group(1):
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else size - 1
        else:  # ultimi N byte
            start = max(0, size - int(m.group(2)))
        end = min(end, size - 1)
        if start > end:
            raise HTTPException(status.HTTP_416_RANGE_NOT_SATISFIABLE, "Range non valido")
        partial = True

    obj = storage.get(asset.storage_key, f"bytes={start}-{end}" if partial else None)
    body = obj["Body"]

    if download:
        # Il download completo resta tracciato; le richieste Range del player no.
        audit(
            ctx.db,
            "asset.downloaded",
            request=request,
            user_id=ctx.user.id,
            workspace_id=ctx.workspace_id,
            object_type="asset",
            object_id=asset.id,
        )
        ctx.db.commit()

    disposition = "attachment" if download else "inline"
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
        "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(asset.filename)}",
        "Cache-Control": "private, no-store",
    }
    # Tutto ciò che il browser potrebbe eseguire (HTML delle pagine salvate, SVG...) resta
    # isolato. I PDF fanno eccezione: il visualizzatore del browser non funziona in sandbox.
    if asset.mime_type != "application/pdf":
        headers["Content-Security-Policy"] = "sandbox"
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(
        body.iter_chunks(storage.CHUNK),
        status_code=206 if partial else 200,
        media_type=asset.mime_type,
        headers=headers,
    )
