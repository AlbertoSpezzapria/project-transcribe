"""Autenticazione: password + 2FA TOTP obbligatoria.

Flusso:
1. POST /auth/login → sessione "a metà" (mfa_verified = false, scadenza breve).
2a. Utente senza 2FA: POST /auth/2fa/setup, poi POST /auth/2fa/enable con il primo codice.
2b. Utente con 2FA: POST /auth/2fa/verify con codice TOTP o di recupero.
3. La sessione diventa piena (mfa_verified = true) e dura session_ttl_hours.
"""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app import security
from app.audit import audit, client_ip
from app.config import get_settings
from app.db import get_db
from app.deps import current_session, now, require_session, require_user
from app.models import Membership, RecoveryCode, User
from app.models import Session as SessionRow
from app.ratelimit import login_limiter, mfa_limiter
from app.schemas import (
    AuthState,
    ChangePasswordRequest,
    LoginRequest,
    MfaCode,
    MfaEnableResponse,
    MfaSetupResponse,
    UserOut,
    WorkspaceOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_GENERIC_LOGIN_ERROR = "Email o password non corretti"


def _set_cookie(response: Response, token: str, max_age: int) -> None:
    s = get_settings()
    response.set_cookie(
        s.session_cookie_name,
        token,
        max_age=max_age,
        httponly=True,
        secure=s.cookie_secure,
        samesite="strict",
        path="/",
    )


def _state(db: Session, row: SessionRow | None) -> AuthState:
    if row is None:
        return AuthState(authenticated=False, step="none")
    user = row.user
    if not user.totp_enabled:
        return AuthState(authenticated=False, step="mfa_setup", user=UserOut.model_validate(user))
    if not row.mfa_verified:
        return AuthState(authenticated=False, step="mfa_verify", user=UserOut.model_validate(user))
    memberships = db.scalars(select(Membership).where(Membership.user_id == user.id)).all()
    return AuthState(
        authenticated=True,
        step="done",
        user=UserOut.model_validate(user),
        workspaces=[
            WorkspaceOut(id=m.workspace_id, name=m.workspace.name, role=m.role)
            for m in sorted(memberships, key=lambda m: m.workspace.name)
        ],
    )


def _promote(row: SessionRow, response: Response, request: Request) -> None:
    """Dopo la 2FA: nuova sessione piena (token ruotato contro la session fixation)."""
    ttl = timedelta(hours=get_settings().session_ttl_hours)
    token, token_hash = security.new_session_token()
    row.token_hash = token_hash
    row.mfa_verified = True
    row.expires_at = now() + ttl
    row.user.last_login_at = now()
    _set_cookie(response, token, int(ttl.total_seconds()))


@router.get("/me", response_model=AuthState)
def me(row: SessionRow | None = Depends(current_session), db: Session = Depends(get_db)):
    return _state(db, row)


@router.post("/login", response_model=AuthState)
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    email = body.email.lower()
    key = f"{email}|{client_ip(request)}"
    if login_limiter.blocked(key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Troppi tentativi. Riprova tra qualche minuto."
        )

    user = db.scalar(select(User).where(User.email == email))
    ok = security.verify_password(user.password_hash if user else None, body.password)
    if not ok or user is None or not user.is_active:
        login_limiter.hit(key)
        audit(db, "auth.login_failed", request=request, user_id=user.id if user else None)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _GENERIC_LOGIN_ERROR)

    login_limiter.reset(key)
    token, token_hash = security.new_session_token()
    ttl = timedelta(minutes=get_settings().session_mfa_pending_minutes)
    row = SessionRow(
        token_hash=token_hash,
        user_id=user.id,
        mfa_verified=False,
        expires_at=now() + ttl,
        ip=client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:400],
    )
    db.add(row)
    audit(db, "auth.password_ok", request=request, user_id=user.id)
    db.commit()
    db.refresh(row)
    _set_cookie(response, token, int(ttl.total_seconds()))
    return _state(db, row)


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    row: SessionRow | None = Depends(current_session),
    db: Session = Depends(get_db),
):
    if row is not None:
        db.delete(row)
        db.commit()
    response.delete_cookie(get_settings().session_cookie_name, path="/")


@router.post("/2fa/setup", response_model=MfaSetupResponse)
def mfa_setup(row: SessionRow = Depends(require_session), db: Session = Depends(get_db)):
    user = row.user
    if user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Verifica in due passaggi già attiva")
    # Idempotente anche con richieste concorrenti: la chiave si scrive solo se manca
    # (UPDATE condizionato, atomico in Postgres), poi si rilegge quella che ha vinto.
    if not user.totp_secret_enc:
        db.execute(
            update(User)
            .where(User.id == user.id, User.totp_secret_enc.is_(None))
            .values(totp_secret_enc=security.encrypt(security.new_totp_secret()))
        )
        db.commit()
        db.refresh(user)
    secret = security.decrypt(user.totp_secret_enc)
    return MfaSetupResponse(secret=secret, otpauth_uri=security.totp_uri(secret, user.email))


@router.post("/2fa/enable", response_model=MfaEnableResponse)
def mfa_enable(
    body: MfaCode,
    request: Request,
    response: Response,
    row: SessionRow = Depends(require_session),
    db: Session = Depends(get_db),
):
    user = row.user
    if user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Verifica in due passaggi già attiva")
    if not user.totp_secret_enc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Avvia prima la configurazione")
    if mfa_limiter.blocked(str(user.id)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Troppi tentativi")
    if not security.verify_totp(security.decrypt(user.totp_secret_enc), body.code):
        mfa_limiter.hit(str(user.id))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Codice non valido")

    mfa_limiter.reset(str(user.id))
    user.totp_enabled = True
    codes = security.new_recovery_codes()
    db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    db.add_all(RecoveryCode(user_id=user.id, code_hash=security.hash_recovery_code(c)) for c in codes)
    _promote(row, response, request)
    audit(db, "auth.mfa_enabled", request=request, user_id=user.id)
    db.commit()
    return MfaEnableResponse(recovery_codes=codes)


@router.post("/2fa/verify", response_model=AuthState)
def mfa_verify(
    body: MfaCode,
    request: Request,
    response: Response,
    row: SessionRow = Depends(require_session),
    db: Session = Depends(get_db),
):
    user = row.user
    if not user.totp_enabled or not user.totp_secret_enc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Verifica in due passaggi non attiva")
    if mfa_limiter.blocked(str(user.id)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Troppi tentativi")

    method = "totp"
    ok = security.verify_totp(security.decrypt(user.totp_secret_enc), body.code)
    if not ok:
        # Codice di recupero monouso
        result = db.execute(
            update(RecoveryCode)
            .where(
                RecoveryCode.user_id == user.id,
                RecoveryCode.code_hash == security.hash_recovery_code(body.code),
                RecoveryCode.used_at.is_(None),
            )
            .values(used_at=now())
        )
        ok = result.rowcount == 1
        method = "recovery_code"
    if not ok:
        mfa_limiter.hit(str(user.id))
        audit(db, "auth.mfa_failed", request=request, user_id=user.id)
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Codice non valido")

    mfa_limiter.reset(str(user.id))
    _promote(row, response, request)
    audit(db, "auth.login", request=request, user_id=user.id, method=method)
    db.commit()
    return _state(db, row)


@router.post("/password", status_code=204)
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    row: SessionRow = Depends(require_session),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if not security.verify_password(user.password_hash, body.current_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password attuale non corretta")
    problems = security.password_problems(body.new_password)
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, " ".join(problems))
    user.password_hash = security.hash_password(body.new_password)
    # Chiude tutte le altre sessioni dell'utente
    db.execute(delete(SessionRow).where(SessionRow.user_id == user.id, SessionRow.id != row.id))
    audit(db, "auth.password_changed", request=request, user_id=user.id)
    db.commit()
