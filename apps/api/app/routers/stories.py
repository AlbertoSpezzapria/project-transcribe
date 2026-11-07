import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select

from app.audit import audit
from app.deps import WorkspaceContext, workspace_context
from app.models import Source, Story, StorySource
from app.routers.sources import source_out
from app.schemas import SourceOut, StoryCreate, StoryOut, StoryUpdate

router = APIRouter(prefix="/workspaces/{workspace_id}/stories", tags=["stories"])


def _get_story(ctx: WorkspaceContext, story_id: uuid.UUID) -> Story:
    # La RLS garantisce già l'isolamento; il filtro esplicito è una seconda difesa.
    story = ctx.db.scalar(select(Story).where(Story.id == story_id, Story.workspace_id == ctx.workspace_id))
    if story is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Storia non trovata")
    return story


def _out(story: Story, count: int) -> StoryOut:
    out = StoryOut.model_validate(story)
    out.source_count = count
    return out


@router.get("", response_model=list[StoryOut])
def list_stories(ctx: WorkspaceContext = Depends(workspace_context)):
    counts = select(StorySource.story_id, func.count().label("n")).group_by(StorySource.story_id).subquery()
    rows = ctx.db.execute(
        select(Story, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.story_id == Story.id)
        .where(Story.workspace_id == ctx.workspace_id)
        .order_by(Story.updated_at.desc())
    ).all()
    return [_out(s, n) for s, n in rows]


@router.post("", response_model=StoryOut, status_code=201)
def create_story(body: StoryCreate, request: Request, ctx: WorkspaceContext = Depends(workspace_context)):
    story = Story(
        workspace_id=ctx.workspace_id,
        title=body.title.strip(),
        description=body.description,
        created_by=ctx.user.id,
    )
    ctx.db.add(story)
    ctx.db.flush()
    audit(
        ctx.db,
        "story.created",
        request=request,
        user_id=ctx.user.id,
        workspace_id=ctx.workspace_id,
        object_type="story",
        object_id=story.id,
    )
    ctx.db.commit()
    return _out(story, 0)


@router.get("/{story_id}", response_model=StoryOut)
def get_story(story_id: uuid.UUID, ctx: WorkspaceContext = Depends(workspace_context)):
    story = _get_story(ctx, story_id)
    n = ctx.db.scalar(select(func.count()).where(StorySource.story_id == story.id)) or 0
    return _out(story, n)


@router.patch("/{story_id}", response_model=StoryOut)
def update_story(story_id: uuid.UUID, body: StoryUpdate, ctx: WorkspaceContext = Depends(workspace_context)):
    story = _get_story(ctx, story_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(story, field, value)
    ctx.db.commit()
    return get_story(story_id, ctx)


@router.get("/{story_id}/sources", response_model=list[SourceOut])
def story_sources(story_id: uuid.UUID, ctx: WorkspaceContext = Depends(workspace_context)):
    _get_story(ctx, story_id)
    sources = ctx.db.scalars(
        select(Source)
        .join(StorySource, StorySource.source_id == Source.id)
        .where(StorySource.story_id == story_id)
        .order_by(Source.created_at.desc())
    ).all()
    return [source_out(ctx, s) for s in sources]


@router.put("/{story_id}/sources/{source_id}", status_code=204)
def attach_source(
    story_id: uuid.UUID, source_id: uuid.UUID, ctx: WorkspaceContext = Depends(workspace_context)
):
    _get_story(ctx, story_id)
    if ctx.db.get(Source, source_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fonte non trovata")
    if ctx.db.get(StorySource, {"story_id": story_id, "source_id": source_id}) is None:
        ctx.db.add(StorySource(workspace_id=ctx.workspace_id, story_id=story_id, source_id=source_id))
        ctx.db.commit()


@router.delete("/{story_id}/sources/{source_id}", status_code=204)
def detach_source(
    story_id: uuid.UUID, source_id: uuid.UUID, ctx: WorkspaceContext = Depends(workspace_context)
):
    link = ctx.db.get(StorySource, {"story_id": story_id, "source_id": source_id})
    if link is not None:
        ctx.db.delete(link)
        ctx.db.commit()
