"""Modello dati.

Le tabelle con `workspace_id` sono protette da Row-Level Security (vedi migrazione 0001):
anche un errore nell'API non può far leggere dati di un altro workspace.
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


# --- Enum -------------------------------------------------------------------


class Role(str, enum.Enum):
    owner = "owner"  # gestisce il workspace e i membri
    editor = "editor"  # caporedattore
    journalist = "journalist"  # redattore


class StoryStatus(str, enum.Enum):
    active = "active"
    published = "published"
    archived = "archived"


class SourceType(str, enum.Enum):
    audio = "audio"
    video = "video"
    document = "document"
    web = "web"
    note = "note"


class Confidentiality(str, enum.Enum):
    normal = "normal"
    confidential = "confidential"  # solo modelli locali
    secret = "secret"  # solo modelli locali, escluso da log e anteprime


class SourceStatus(str, enum.Enum):
    uploaded = "uploaded"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class AssetKind(str, enum.Enum):
    original = "original"
    derived = "derived"


class JobStatus(str, enum.Enum):
    """Stato di un passo della pipeline (trascrizione, versione pulita)."""

    none = "none"
    queued = "queued"
    processing = "processing"
    ready = "ready"
    failed = "failed"


# --- Identità e accesso (senza RLS: servono prima di conoscere il workspace) ---


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    totp_secret_enc: Mapped[str | None] = mapped_column(Text)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user")


class RecoveryCode(Base):
    __tablename__ = "recovery_codes"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    mfa_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))

    user: Mapped[User] = relationship()


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = _created_at()

    memberships: Mapped[list["Membership"]] = relationship(back_populates="workspace")


class Membership(Base):
    __tablename__ = "memberships"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[Role] = mapped_column(_enum(Role, "role"), nullable=False)
    created_at: Mapped[datetime] = _created_at()

    workspace: Mapped[Workspace] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


# --- Dati di lavoro (con RLS per workspace) -----------------------------------


class Story(Base):
    __tablename__ = "stories"
    __table_args__ = (UniqueConstraint("workspace_id", "id", name="uq_stories_ws_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[StoryStatus] = mapped_column(
        _enum(StoryStatus, "story_status"), default=StoryStatus.active, nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("workspace_id", "id", name="uq_sources_ws_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    type: Mapped[SourceType] = mapped_column(_enum(SourceType, "source_type"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    # Data dell'intervista o del documento (non del caricamento): asse temporale del grafo.
    source_date: Mapped[date | None] = mapped_column(Date)
    confidentiality: Mapped[Confidentiality] = mapped_column(
        _enum(Confidentiality, "confidentiality"), default=Confidentiality.normal, nullable=False
    )
    status: Mapped[SourceStatus] = mapped_column(
        _enum(SourceStatus, "source_status"), default=SourceStatus.uploaded, nullable=False
    )
    status_detail: Mapped[str | None] = mapped_column(String(500))
    meta: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    note_text: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    assets: Mapped[list["Asset"]] = relationship(
        back_populates="source", cascade="all, delete-orphan", passive_deletes=True
    )


class StorySource(Base):
    """Collegamento storia ↔ fonte. Le FK composte impediscono di collegare
    oggetti di workspace diversi."""

    __tablename__ = "story_sources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "story_id"],
            ["stories.workspace_id", "stories.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "source_id"],
            ["sources.workspace_id", "sources.id"],
            ondelete="CASCADE",
        ),
        Index("ix_story_sources_source", "source_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    story_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    added_at: Mapped[datetime] = _created_at()


class Asset(Base):
    """File collegato a una fonte. L'originale è immutabile e identificato dal suo hash."""

    __tablename__ = "assets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "source_id"],
            ["sources.workspace_id", "sources.id"],
            ondelete="CASCADE",
        ),
        Index("ix_assets_source", "source_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[AssetKind] = mapped_column(_enum(AssetKind, "asset_kind"), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(150), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = _created_at()

    source: Mapped[Source] = relationship(back_populates="assets")


class Transcript(Base):
    """Una versione della trascrizione di una fonte audio/video.

    Ritrascrivere crea una nuova versione: le correzioni fatte sulla precedente
    non vengono mai sovrascritte. `is_current` indica quella mostrata.
    """

    __tablename__ = "transcripts"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_transcripts_ws_id"),
        ForeignKeyConstraint(
            ["workspace_id", "source_id"],
            ["sources.workspace_id", "sources.id"],
            ondelete="CASCADE",
        ),
        Index("ix_transcripts_source", "source_id"),
        Index("uq_transcripts_current", "source_id", unique=True, postgresql_where=text("is_current")),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        _enum(JobStatus, "job_status"), default=JobStatus.queued, nullable=False
    )
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    error: Mapped[str | None] = mapped_column(String(500))
    engine: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    language: Mapped[str | None] = mapped_column(String(10))  # richiesta (None = automatica)
    detected_language: Mapped[str | None] = mapped_column(String(10))
    duration: Mapped[float | None] = mapped_column(Float)
    diarized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Forma d'onda ridotta (picchi normalizzati 0..1) per il player
    peaks: Mapped[list | None] = mapped_column(JSONB)
    clean_status: Mapped[JobStatus] = mapped_column(
        _enum(JobStatus, "job_status"), default=JobStatus.none, nullable=False
    )
    clean_model: Mapped[str | None] = mapped_column(String(100))
    clean_error: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _created_at()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Speaker(Base):
    """Interlocutore dentro una trascrizione (SPEAKER_00 → "Mario Rossi")."""

    __tablename__ = "speakers"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_speakers_ws_id"),
        ForeignKeyConstraint(
            ["workspace_id", "transcript_id"],
            ["transcripts.workspace_id", "transcripts.id"],
            ondelete="CASCADE",
        ),
        Index("ix_speakers_transcript", "transcript_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    transcript_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    label: Mapped[str] = mapped_column(String(50), nullable=False)  # dato dalla diarization
    name: Mapped[str | None] = mapped_column(String(200))  # dato dal giornalista
    created_at: Mapped[datetime] = _created_at()


class Segment(Base):
    """Unità citabile: un turno di parola con i tempi di ogni parola.

    `text_raw` è il verbatim del modello e non cambia mai; `text_edited` contiene
    le correzioni umane; `text_clean` è la versione leggibile, derivata e mai usata
    per le citazioni.
    """

    __tablename__ = "segments"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_segments_ws_id"),
        UniqueConstraint("transcript_id", "idx", name="uq_segments_transcript_idx"),
        ForeignKeyConstraint(
            ["workspace_id", "transcript_id"],
            ["transcripts.workspace_id", "transcripts.id"],
            ondelete="CASCADE",
        ),
        # Se lo speaker viene eliminato resta il segmento, senza speaker.
        ForeignKeyConstraint(
            ["workspace_id", "speaker_id"],
            ["speakers.workspace_id", "speakers.id"],
            ondelete="SET NULL (speaker_id)",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    transcript_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    start: Mapped[float] = mapped_column(Float, nullable=False)
    end: Mapped[float] = mapped_column(Float, nullable=False)
    speaker_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    text_raw: Mapped[str] = mapped_column(Text, nullable=False)
    text_edited: Mapped[str | None] = mapped_column(Text)
    text_clean: Mapped[str | None] = mapped_column(Text)
    # [{"w": "parola", "s": 1.23, "e": 1.57, "p": 0.98}, ...]
    words: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    edited_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    """Chi ha fatto cosa. Mai contenuti delle fonti, solo identificativi."""

    __tablename__ = "audit_log"
    # Niente RETURNING: con la RLS, rileggere gli eventi senza workspace non è permesso.
    __table_args__ = {"implicit_returning": False}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    object_type: Mapped[str | None] = mapped_column(String(50))
    object_id: Mapped[str | None] = mapped_column(String(100))
    ip: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = _created_at()


# Tabelle protette da RLS: usato dalla migrazione e dai test.
RLS_TABLES = [
    "stories",
    "sources",
    "story_sources",
    "assets",
    "transcripts",
    "speakers",
    "segments",
    "audit_log",
]
