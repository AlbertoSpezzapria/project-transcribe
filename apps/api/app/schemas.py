import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import Confidentiality, JobStatus, Role, SourceStatus, SourceType, StoryStatus


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Auth ---------------------------------------------------------------------


class LoginRequest(BaseModel):
    # Nessuna validazione di formato al login: basta il confronto con l'account esistente.
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)


class MfaCode(BaseModel):
    code: str = Field(min_length=6, max_length=20, description="Codice TOTP o codice di recupero")


class MfaSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class MfaEnableResponse(BaseModel):
    recovery_codes: list[str] = Field(description="Mostrati una sola volta")


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=1, max_length=200)


class UserOut(ORM):
    id: uuid.UUID
    email: str
    full_name: str


class WorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    role: Role


class AuthState(BaseModel):
    """Stato della sessione: il frontend decide quale schermata mostrare."""

    authenticated: bool
    step: str = Field(description="none | mfa_setup | mfa_verify | done")
    user: UserOut | None = None
    workspaces: list[WorkspaceOut] = []


# --- Workspace ----------------------------------------------------------------


class MemberOut(BaseModel):
    user: UserOut
    role: Role


# --- Storie ---------------------------------------------------------------------


class StoryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)


class StoryUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    status: StoryStatus | None = None


class StoryOut(ORM):
    id: uuid.UUID
    title: str
    description: str | None
    status: StoryStatus
    created_at: datetime
    updated_at: datetime
    source_count: int = 0


# --- Fonti --------------------------------------------------------------------


class AssetOut(ORM):
    id: uuid.UUID
    kind: str
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    created_at: datetime


class SourceOut(ORM):
    id: uuid.UUID
    type: SourceType
    title: str
    source_date: date | None
    confidentiality: Confidentiality
    status: SourceStatus
    status_detail: str | None
    note_text: str | None
    meta: dict = Field(serialization_alias="metadata")
    created_at: datetime
    assets: list[AssetOut] = []
    story_ids: list[uuid.UUID] = []


class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=200_000)
    source_date: date | None = None
    confidentiality: Confidentiality = Confidentiality.normal
    story_id: uuid.UUID | None = None


class SourceUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    source_date: date | None = None
    confidentiality: Confidentiality | None = None
    metadata: dict | None = None


# --- Trascrizioni ----------------------------------------------------------------


class SpeakerOut(ORM):
    id: uuid.UUID
    label: str
    name: str | None


class SegmentOut(ORM):
    id: uuid.UUID
    idx: int
    start: float
    end: float
    speaker_id: uuid.UUID | None
    text_raw: str
    text_edited: str | None
    text_clean: str | None
    words: list[tuple[str, float, float, float]] = Field(description="[parola, inizio, fine, probabilità]")
    edited_at: datetime | None


class TranscriptSummary(ORM):
    id: uuid.UUID
    is_current: bool
    status: JobStatus
    progress: float
    error: str | None
    engine: str
    model: str
    language: str | None
    detected_language: str | None
    duration: float | None
    diarized: bool
    clean_status: JobStatus
    clean_model: str | None
    clean_error: str | None
    created_at: datetime
    completed_at: datetime | None


class TranscriptOut(TranscriptSummary):
    peaks: list[float] | None
    speakers: list[SpeakerOut]
    segments: list[SegmentOut]
    # Nuova versione in preparazione (diventa corrente quando è pronta)
    pending: TranscriptSummary | None = None
    clean_available: bool
    clean_unavailable_reason: str | None = None


class SegmentUpdate(BaseModel):
    text: str | None = Field(
        default=None, max_length=20_000, description="Testo corretto; null torna al verbatim"
    )
    speaker_id: uuid.UUID | None = None


class SpeakerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class SpeakerUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)


class SpeakerMerge(BaseModel):
    into_id: uuid.UUID


class TranscribeRequest(BaseModel):
    language: str | None = Field(
        default=None, pattern=r"^[a-z]{2}$", description="Codice ISO 639-1; null = automatica"
    )
