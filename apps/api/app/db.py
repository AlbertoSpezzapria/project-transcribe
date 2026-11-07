"""Connessione al database e contesto di workspace per la Row-Level Security.

Ogni transazione apre con `set_config('app.workspace_id', ..., true)` se la sessione
è legata a un workspace: le policy RLS filtrano le righe su quel valore. Senza
workspace impostato le tabelle protette risultano vuote.
"""

import uuid
from collections.abc import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

_WS_KEY = "workspace_id"


@event.listens_for(Session, "after_begin")
def _apply_workspace_context(session: Session, transaction, connection) -> None:
    ws = session.info.get(_WS_KEY)
    connection.execute(
        text("select set_config('app.workspace_id', :ws, true)"),
        {"ws": str(ws) if ws else ""},
    )


def bind_workspace(db: Session, workspace_id: uuid.UUID | None) -> None:
    """Lega la sessione a un workspace. Vale anche per le transazioni successive."""
    db.info[_WS_KEY] = workspace_id
    if db.in_transaction():
        db.execute(
            text("select set_config('app.workspace_id', :ws, true)"),
            {"ws": str(workspace_id) if workspace_id else ""},
        )


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
