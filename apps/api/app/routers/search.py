"""Ricerca nell'archivio e domande con risposta citata."""

import uuid
from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app import llm
from app import search as engine
from app.audit import audit
from app.deps import WorkspaceContext, workspace_context
from app.models import SourceType
from app.schemas import AskRequest, AskResponse, SearchHit, SearchResponse

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["search"])


def _hit(h: engine.Hit) -> SearchHit:
    data = asdict(h)
    data.pop("text")
    return SearchHit(**data)


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(min_length=1, max_length=500),
    type: SourceType | None = None,
    story_id: uuid.UUID | None = None,
    source_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=30, ge=1, le=100),
    ctx: WorkspaceContext = Depends(workspace_context),
):
    filters = engine.Filters(type, story_id, source_id, date_from, date_to)
    hits, semantic = engine.search(ctx.db, q, filters, limit=limit)
    return SearchResponse(results=[_hit(h) for h in hits], semantic=semantic)


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, request: Request, ctx: WorkspaceContext = Depends(workspace_context)):
    filters = engine.Filters(body.type, body.story_id, None, body.date_from, body.date_to)
    try:
        result = engine.ask(ctx.db, body.question, filters)
    except llm.LlmError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    # Nel registro solo chi ha chiesto e quale modello ha risposto, mai la domanda
    audit(
        ctx.db,
        "archive.asked",
        request=request,
        user_id=ctx.user.id,
        workspace_id=ctx.workspace_id,
        model=result.model,
        passages=len(result.passages),
    )
    ctx.db.commit()
    return AskResponse(
        answer=result.answer,
        insufficient=result.insufficient,
        passages=[_hit(h) for h in result.passages],
        unverified_quotes=result.unverified_quotes,
        model=result.model,
        unavailable_reason=result.unavailable_reason,
    )
