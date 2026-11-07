from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.deps import WorkspaceContext, workspace_context
from app.models import Membership
from app.schemas import MemberOut, UserOut

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["workspaces"])


@router.get("/members", response_model=list[MemberOut])
def list_members(ctx: WorkspaceContext = Depends(workspace_context)):
    rows = ctx.db.scalars(select(Membership).where(Membership.workspace_id == ctx.workspace_id)).all()
    return [
        MemberOut(user=UserOut.model_validate(m.user), role=m.role)
        for m in sorted(rows, key=lambda m: m.user.full_name)
    ]
