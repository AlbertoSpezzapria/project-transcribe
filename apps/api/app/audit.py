import uuid

from fastapi import Request
from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.models import AuditLog


def client_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host


def audit(
    db: Session,
    action: str,
    *,
    request: Request | None = None,
    user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    object_type: str | None = None,
    object_id: uuid.UUID | str | None = None,
    **details: object,
) -> None:
    """Registra un evento. Mai contenuti delle fonti nei `details`.

    INSERT senza RETURNING: con la RLS, RETURNING richiederebbe di poter rileggere la riga
    (gli eventi senza workspace non sono leggibili dall'applicazione, per scelta).
    """
    db.execute(
        insert(AuditLog.__table__).values(
            action=action,
            user_id=user_id,
            workspace_id=workspace_id,
            object_type=object_type,
            object_id=str(object_id) if object_id else None,
            ip=client_ip(request),
            details={k: v for k, v in details.items() if v is not None},
        )
    )
