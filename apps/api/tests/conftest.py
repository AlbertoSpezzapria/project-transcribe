"""I test girano su un database e un bucket dedicati, ricreati a ogni esecuzione.

docker compose run --rm api pytest
"""

import os
import re

import psycopg
import pyotp
import pytest

TEST_DB = "redazione_test"


def _swap_db(url: str, name: str) -> str:
    return re.sub(r"/[^/]+$", f"/{name}", url)


os.environ["DATABASE_URL"] = _swap_db(os.environ["DATABASE_URL"], TEST_DB)
os.environ["MIGRATIONS_DATABASE_URL"] = _swap_db(os.environ["MIGRATIONS_DATABASE_URL"], TEST_DB)
os.environ["S3_BUCKET"] = "redazione-test"
os.environ["ENV"] = "test"
os.environ["STT_ENGINE"] = "fake"
# Nessun embedder nei test: la ricerca per significato si prova con un embedding finto
os.environ["EMBEDDER_URL"] = "http://127.0.0.1:9"
os.environ["DIARIZATION_ENABLED"] = "false"
for _k in (
    "LLM_CLOUD_API_KEY",
    "LLM_CLOUD_MODEL",
    "LLM_CLOUD_FAST_MODEL",
    "LLM_CLOUD_STRONG_MODEL",
    "LLM_LOCAL_BASE_URL",
    "LLM_LOCAL_MODEL",
):
    os.environ.pop(_k, None)


def _recreate_database() -> None:
    owner = os.environ["MIGRATIONS_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    admin = _swap_db(owner, "postgres")
    app_role = os.environ.get("APP_DB_USER", "redazione_app")
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        conn.execute(f"CREATE DATABASE {TEST_DB}")
        conn.execute(f"GRANT CONNECT ON DATABASE {TEST_DB} TO {app_role}")
    with psycopg.connect(owner, autocommit=True) as conn:
        conn.execute(f"GRANT USAGE ON SCHEMA public TO {app_role}")


@pytest.fixture(scope="session", autouse=True)
def database():
    _recreate_database()
    from alembic.config import Config

    from alembic import command

    command.upgrade(Config("alembic.ini"), "head")
    yield


@pytest.fixture(scope="session")
def app(database):
    from app.main import app as fastapi_app

    return fastapi_app


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    from app.ratelimit import login_limiter, mfa_limiter

    login_limiter._hits.clear()
    mfa_limiter._hits.clear()
    with TestClient(app, base_url="http://testserver") as c:
        yield c


PASSWORD = "Password-di-prova-1"


def make_user(email: str, workspace_name: str | None = None, role: str = "journalist"):
    """Crea utente (e opzionalmente workspace). Restituisce (user_id, workspace_id)."""
    from app import security
    from app.db import SessionLocal
    from app.models import Membership, Role, User, Workspace

    with SessionLocal() as db:
        user = User(
            email=email, full_name=email.split("@")[0], password_hash=security.hash_password(PASSWORD)
        )
        db.add(user)
        db.flush()
        ws_id = None
        if workspace_name:
            ws = Workspace(name=workspace_name)
            db.add(ws)
            db.flush()
            db.add(Membership(workspace_id=ws.id, user_id=user.id, role=Role(role)))
            ws_id = ws.id
        db.commit()
        return user.id, ws_id


def login_full(client, email: str) -> list[str]:
    """Login completo con configurazione 2FA. Restituisce i codici di recupero."""
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    assert r.json()["step"] == "mfa_setup"
    secret = client.post("/api/auth/2fa/setup").json()["secret"]
    r = client.post("/api/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()})
    assert r.status_code == 200, r.text
    return r.json()["recovery_codes"]
