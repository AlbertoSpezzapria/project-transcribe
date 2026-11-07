import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Path, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import bind_workspace, get_db
from app.models import Membership, Role, User
from app.models import Session as SessionRow
from app.security import hash_token

# Aggiorna last_seen al massimo una volta al minuto per non scrivere a ogni richiesta.
_TOUCH_EVERY = timedelta(minutes=1)


def now() -> datetime:
    return datetime.now(UTC)


def current_session(request: Request, db: Session = Depends(get_db)) -> SessionRow | None:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        return None
    row = db.scalar(select(SessionRow).where(SessionRow.token_hash == hash_token(token)))
    if row is None or row.expires_at <= now() or not row.user.is_active:
        return None
    if row.last_seen_at is None or now() - row.last_seen_at > _TOUCH_EVERY:
        row.last_seen_at = now()
        db.commit()
    return row


def require_session(row: SessionRow | None = Depends(current_session)) -> SessionRow:
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessione non valida o scaduta")
    return row


def require_user(row: SessionRow = Depends(require_session)) -> User:
    """Utente pienamente autenticato: password + 2FA."""
    if not row.mfa_verified or not row.user.totp_enabled:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Verifica in due passaggi richiesta")
    return row.user


@dataclass
class WorkspaceContext:
    user: User
    workspace_id: uuid.UUID
    role: Role
    db: Session

    def require_role(self, *roles: Role) -> None:
        if self.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Permessi insufficienti")


def workspace_context(
    workspace_id: uuid.UUID = Path(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> WorkspaceContext:
    membership = db.get(Membership, {"workspace_id": workspace_id, "user_id": user.id})
    if membership is None:
        # 404 e non 403: non riveliamo l'esistenza di workspace altrui.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace non trovato")
    bind_workspace(db, workspace_id)
    return WorkspaceContext(user=user, workspace_id=workspace_id, role=membership.role, db=db)
