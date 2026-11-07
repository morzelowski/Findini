"""Model danych (SQLAlchemy 2). Schemat tworzą migracje Alembic — patrz alembic/versions.

Zasada: dane publiczne zgłoszenia (`reports`) są oddzielone od prywatnych
(`report_private`: dokładne miejsce, ukryta cecha, pytanie weryfikacyjne).
Publiczne API serializuje wyłącznie jawną listę pól (app/schemas.py).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBEDDING_DIM = 512


class Base(DeclarativeBase):
    pass


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Guest(Base):
    __tablename__ = "guests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    alias: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    recovery_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    recovery_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    banned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ban_reason: Mapped[str | None] = mapped_column(String(300))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    guest_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    guest: Mapped[Guest] = relationship(lazy="joined")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(8))  # lost | found
    status: Mapped[str] = mapped_column(String(12), default="active")
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)
    colors: Mapped[list[str]] = mapped_column(ARRAY(String(16)), default=list)
    occurred_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    occurred_to: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Publiczna (zgrubna) lokalizacja: środek komórki siatki + promień obszaru.
    cell_id: Mapped[str] = mapped_column(String(32))
    public_lat: Mapped[float] = mapped_column(Float)
    public_lon: Mapped[float] = mapped_column(Float)
    area_radius_m: Mapped[int] = mapped_column(Integer)
    area_label: Mapped[str | None] = mapped_column(String(80))
    # Kolumna public_geog (geography) jest generowana w bazie z public_lat/public_lon.

    holding: Mapped[str | None] = mapped_column(String(16))  # with_finder | at_place | office
    holding_note: Mapped[str | None] = mapped_column(String(120))

    search_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hidden_reason: Mapped[str | None] = mapped_column(String(300))

    private: Mapped[ReportPrivate] = relationship(
        back_populates="report", uselist=False, cascade="all, delete-orphan", lazy="joined"
    )
    photos: Mapped[list[Photo]] = relationship(
        back_populates="report",
        order_by="Photo.position",
        lazy="selectin",
        primaryjoin="and_(Report.id == Photo.report_id, Photo.purpose == 'report')",
        viewonly=True,
    )


class ReportPrivate(Base):
    """Dane widoczne wyłącznie dla właściciela zgłoszenia (nigdy w publicznym API ani indeksie)."""

    __tablename__ = "report_private"

    report_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), primary_key=True)
    exact_lat: Mapped[float] = mapped_column(Float)
    exact_lon: Mapped[float] = mapped_column(Float)
    accuracy_m: Mapped[int | None] = mapped_column(Integer)
    uncertainty_m: Mapped[int] = mapped_column(Integer, default=0)
    location_source: Mapped[str] = mapped_column(String(8))  # gps | map
    secret_details: Mapped[str | None] = mapped_column(Text)
    claim_question: Mapped[str | None] = mapped_column(String(200))

    report: Mapped[Report] = relationship(back_populates="private")


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"), index=True)
    report_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("reports.id", ondelete="SET NULL"), index=True)
    claim_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("claims.id", ondelete="SET NULL"), index=True)
    purpose: Mapped[str] = mapped_column(String(12))  # report | evidence
    storage_key: Mapped[str] = mapped_column(String(80))
    thumb_key: Mapped[str] = mapped_column(String(80))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    position: Mapped[int] = mapped_column(SmallInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    embedding = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(64))
    embedding_status: Mapped[str] = mapped_column(String(10), default="pending")
    embedding_attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    embedding_error: Mapped[str | None] = mapped_column(String(200))
    ai_suggestion: Mapped[dict | None] = mapped_column(JSONB)

    report: Mapped[Report | None] = relationship(
        back_populates="photos",
        primaryjoin="Report.id == Photo.report_id",
        foreign_keys=[report_id],
        viewonly=True,
    )


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    report_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    claimant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"), index=True)
    finder_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(12), default="pending")
    answer: Mapped[str] = mapped_column(Text)
    proof_details: Mapped[str] = mapped_column(Text, default="")
    lost_report_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("reports.id", ondelete="SET NULL"))
    finder_note: Mapped[str | None] = mapped_column(String(300))
    handover_code: Mapped[str | None] = mapped_column(String(8))
    handover_attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    finder_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    owner_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_reason: Mapped[str | None] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    report: Mapped[Report] = relationship(foreign_keys=[report_id], lazy="joined")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"))
    sender_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("guests.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(8), default="text")  # text | system
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Thanks(Base):
    __tablename__ = "thanks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), unique=True)
    from_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("guests.id", ondelete="SET NULL"))
    to_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("guests.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Block(Base):
    __tablename__ = "blocks"

    blocker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"), primary_key=True)
    blocked_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AbuseReport(Base):
    __tablename__ = "abuse_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    reporter_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("guests.id", ondelete="SET NULL"))
    target_type: Mapped[str] = mapped_column(String(10))  # report | claim | message
    target_id: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(String(20))
    details: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(10), default="open")
    resolution_note: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    """Dziennik zmian stanów (bez treści prywatnych)."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    entity: Mapped[str] = mapped_column(String(12))
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    action: Mapped[str] = mapped_column(String(32))
    from_status: Mapped[str | None] = mapped_column(String(12))
    to_status: Mapped[str | None] = mapped_column(String(12))


class ClaimRead(Base):
    __tablename__ = "claim_reads"

    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), primary_key=True)
    guest_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"), primary_key=True)
    last_read_id: Mapped[int] = mapped_column(BigInteger, default=0)
