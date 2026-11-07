"""Comandi di amministrazione.

Durante il pilota non c'è registrazione libera: gli account si creano da qui.

    python -m app.cli gen-key
    python -m app.cli create-workspace "Redazione Cronaca"
    python -m app.cli create-user mario.rossi@example.com "Mario Rossi" --workspace <id> --role journalist
    python -m app.cli add-member <email> <workspace_id> --role editor
    python -m app.cli reset-2fa <email>
"""

import secrets
import uuid

import typer
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from app import security
from app.config import get_settings
from app.models import Membership, RecoveryCode, Role, User, Workspace
from app.models import Session as SessionRow

cli = typer.Typer(no_args_is_help=True, help="Amministrazione di Redazione")


def _db() -> Session:
    # Le tabelle di identità non hanno RLS: basta il ruolo applicativo.
    return Session(create_engine(get_settings().database_url))


@cli.command("gen-key")
def gen_key() -> None:
    """Genera una SECRET_KEY (Fernet)."""
    typer.echo(Fernet.generate_key().decode())


@cli.command("create-workspace")
def create_workspace(name: str) -> None:
    with _db() as db:
        ws = Workspace(name=name)
        db.add(ws)
        db.commit()
        typer.echo(f"Workspace creato: {ws.id}")


@cli.command("create-user")
def create_user(
    email: str,
    full_name: str,
    workspace: uuid.UUID | None = typer.Option(None, help="Workspace a cui aggiungerlo"),
    role: Role = typer.Option(Role.journalist),
    password: str | None = typer.Option(None, help="Se omessa ne viene generata una"),
) -> None:
    password = password or secrets.token_urlsafe(12) + "aA1"
    problems = security.password_problems(password)
    if problems:
        raise typer.BadParameter(" ".join(problems))
    with _db() as db:
        user = User(email=email.lower(), full_name=full_name, password_hash=security.hash_password(password))
        db.add(user)
        db.flush()
        if workspace:
            db.add(Membership(workspace_id=workspace, user_id=user.id, role=role))
        db.commit()
        typer.echo(f"Utente creato: {user.id}")
        typer.echo(f"Password provvisoria: {password}")
        typer.echo("Al primo accesso l'utente dovrà configurare la verifica in due passaggi.")


@cli.command("add-member")
def add_member(email: str, workspace: uuid.UUID, role: Role = typer.Option(Role.journalist)):
    with _db() as db:
        user = db.scalar(select(User).where(User.email == email.lower()))
        if user is None:
            raise typer.BadParameter("Utente non trovato")
        db.merge(Membership(workspace_id=workspace, user_id=user.id, role=role))
        db.commit()
        typer.echo("Fatto.")


@cli.command("reset-2fa")
def reset_2fa(email: str) -> None:
    """Disattiva la 2FA (telefono perso): al prossimo accesso andrà riconfigurata."""
    with _db() as db:
        user = db.scalar(select(User).where(User.email == email.lower()))
        if user is None:
            raise typer.BadParameter("Utente non trovato")
        user.totp_enabled = False
        user.totp_secret_enc = None
        db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
        db.execute(delete(SessionRow).where(SessionRow.user_id == user.id))
        db.commit()
        typer.echo("2FA azzerata e sessioni chiuse.")


@cli.command("seed-dev")
def seed_dev() -> None:
    """Solo sviluppo: workspace e utente di prova (credenziali da DEV_USER_EMAIL / DEV_USER_PASSWORD)."""
    import os

    if get_settings().is_production:
        raise typer.Exit("Non disponibile in produzione")
    email = os.environ.get("DEV_USER_EMAIL", "redattore@redazione.test")
    password = os.environ.get("DEV_USER_PASSWORD")
    if not password:
        raise typer.BadParameter("Imposta DEV_USER_PASSWORD in .env")
    with _db() as db:
        if db.scalar(select(User).where(User.email == email)):
            typer.echo("Utente di prova già presente.")
            return
        ws = Workspace(name="Redazione di prova")
        user = User(
            email=email, full_name="Redattore di prova", password_hash=security.hash_password(password)
        )
        db.add_all([ws, user])
        db.flush()
        db.add(Membership(workspace_id=ws.id, user_id=user.id, role=Role.owner))
        db.commit()
        typer.echo(f"Creati workspace '{ws.name}' e utente {email}.")


if __name__ == "__main__":
    cli()
