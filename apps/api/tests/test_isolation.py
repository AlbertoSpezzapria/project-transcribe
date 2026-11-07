"""L'isolamento tra workspace è garantito dal database (RLS), non solo dall'API."""

import uuid

import pytest
from conftest import login_full, make_user
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.db import SessionLocal, bind_workspace
from app.models import Source, SourceType, Story, StorySource


def test_other_workspace_is_not_found(client):
    make_user("a@example.com", "WS A")
    _, ws_b = make_user("b@example.com", "WS B")
    login_full(client, "a@example.com")
    assert client.get(f"/api/workspaces/{ws_b}/stories").status_code == 404
    assert client.get(f"/api/workspaces/{ws_b}/sources").status_code == 404


def _story(ws: uuid.UUID, title: str) -> uuid.UUID:
    with SessionLocal() as db:
        bind_workspace(db, ws)
        s = Story(workspace_id=ws, title=title)
        db.add(s)
        db.commit()
        return s.id


def test_rls_filters_rows_without_api():
    _, ws1 = make_user("rls1@example.com", "RLS 1")
    _, ws2 = make_user("rls2@example.com", "RLS 2")
    s1 = _story(ws1, "Segreta del workspace 1")
    _story(ws2, "Storia del workspace 2")

    with SessionLocal() as db:
        # Nessun workspace impostato → nessuna riga visibile
        assert db.scalars(select(Story)).all() == []
        bind_workspace(db, ws2)
        titles = [s.title for s in db.scalars(select(Story))]
        assert "Segreta del workspace 1" not in titles
        assert db.get(Story, s1) is None
        # Anche una query "dimenticata" senza filtro non vede l'altro workspace
        n = db.execute(text("select count(*) from stories where id = :id"), {"id": s1}).scalar()
        assert n == 0


def test_rls_blocks_writes_into_other_workspace():
    _, ws1 = make_user("w1@example.com", "W 1")
    _, ws2 = make_user("w2@example.com", "W 2")
    with SessionLocal() as db:
        bind_workspace(db, ws2)
        db.add(Story(workspace_id=ws1, title="Intrusione"))
        with pytest.raises(DBAPIError, match="row-level security"):
            db.commit()


def test_cannot_link_objects_across_workspaces():
    """Le FK composte impediscono collegamenti tra workspace diversi."""
    _, ws1 = make_user("l1@example.com", "L 1")
    story_ws1 = _story(ws1, "Storia")
    _, ws2 = make_user("l2@example.com", "L 2")
    with SessionLocal() as db:
        bind_workspace(db, ws2)
        src = Source(workspace_id=ws2, type=SourceType.note, title="n", meta={})
        db.add(src)
        db.flush()
        db.add(StorySource(workspace_id=ws2, story_id=story_ws1, source_id=src.id))
        with pytest.raises(IntegrityError):
            db.commit()


def test_audit_log_is_append_only():
    _, ws = make_user("audit@example.com", "Audit")
    with SessionLocal() as db:
        bind_workspace(db, ws)
        db.execute(
            text("insert into audit_log (workspace_id, action, details) values (:ws, 'x', '{}')"), {"ws": ws}
        )
        db.commit()
        with pytest.raises(DBAPIError, match="permission denied"):
            db.execute(text("delete from audit_log"))
