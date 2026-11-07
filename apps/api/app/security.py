"""Primitive di sicurezza: password, token di sessione, 2FA TOTP, cifratura dei segreti."""

import hashlib
import hmac
import secrets

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

_hasher = PasswordHasher()  # parametri di default di argon2id (RFC 9106, profilo "low memory")

# Hash fittizio per uniformare i tempi di risposta quando l'utente non esiste.
_DUMMY_HASH = _hasher.hash("password-inesistente")

MIN_PASSWORD_LENGTH = 12


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"La password deve avere almeno {MIN_PASSWORD_LENGTH} caratteri.")
    if password.lower() == password or password.upper() == password:
        problems.append("La password deve contenere lettere maiuscole e minuscole.")
    if not any(c.isdigit() for c in password):
        problems.append("La password deve contenere almeno un numero.")
    return problems


# --- Token di sessione: nel cookie va il token, nel DB solo il suo hash ---------


def new_session_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- Cifratura dei segreti a riposo -------------------------------------------


def _fernet() -> Fernet:
    key = get_settings().secret_key
    if not key:
        raise RuntimeError("SECRET_KEY non configurata")
    return Fernet(key.encode())


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:  # chiave cambiata o dato manomesso
        raise RuntimeError("Impossibile decifrare il segreto") from exc


# --- 2FA TOTP -----------------------------------------------------------------


def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=get_settings().totp_issuer)


def verify_totp(secret: str, code: str) -> bool:
    code = code.replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return False
    # valid_window=1 tollera un piccolo sfasamento dell'orologio del telefono (±30 s)
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def new_recovery_codes(n: int = 10) -> list[str]:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return ["-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3)) for _ in range(n)]


def normalize_recovery_code(code: str) -> str:
    return code.strip().upper().replace(" ", "").replace("-", "")


def hash_recovery_code(code: str) -> str:
    # I codici hanno ~60 bit di entropia: basta un HMAC con la chiave dell'app.
    key = get_settings().secret_key.encode()
    return hmac.new(key, normalize_recovery_code(code).encode(), hashlib.sha256).hexdigest()
