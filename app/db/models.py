"""Core FirstShift entities (design/data-model.md, skeleton subset).

Fields follow the data model exactly, including the O11 hired-to-rota tracking
fields on FirstShift. Tenancy: brand_id everywhere, restaurant_id where the
entity is restaurant-scoped (C-O3). Data minimization: no field without a
named use (C-L3).
"""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    DATE,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# ------------------------------------------------------------------- enums
# Values from design/data-model.md and design/state-machine.md. State enums
# cover the full state machine so the core can persist every state from T3 on.
# Each native Postgres enum type is declared exactly once and shared.

BRANDS = ("lumbre", "pollo")
LANGUAGES = ("es", "pt", "en")
CANDIDATE_SOURCES = ("qr", "job_board", "walk_in", "bench", "referral")
STATES = (
    "new",
    "contacted",
    "consented",
    "screening",
    "matched",
    "interview_booked",
    "interviewed",
    "pending_manager_decision",
    "offer_sent",
    "offer_accepted",
    "preboarding",
    "ready_for_rota",
    "first_shift_scheduled",
    "first_shift_confirmed",
    "first_shift_worked",
    "active_week1",
    "active_day30",
    "benched",
    "withdrawn",
    "no_show",
    "not_selected",
    "erased",
)
ROLES = ("kitchen", "till", "foh", "drive_thru")
OPEN_SHIFT_STATUSES = ("open", "matched", "filled", "cancelled")
CONSENT_CHANNELS = ("whatsapp", "email")
CONSENT_PURPOSES = ("screening", "preboarding", "bench_reengagement")
CONSENT_STATUSES = ("none", "granted", "revoked")
DECISION_TYPES = (
    "shortlist",
    "interview_slot",
    "offer",
    "not_selected",
    "first_shift_slot",
    "backup_activation",
)
ACTOR_TYPES = ("candidate", "manager", "agent", "system", "timer")
CONFIRMATION_STATUSES = ("pending", "confirmed", "unconfirmed")
CURRENT_BLOCKERS = ("none", "docs_missing", "nomina_pending", "rota_locked", "hygiene_pending")
BENCH_REASONS = ("silver_medal", "rehire_eligible", "referral")
BENCH_STATUSES = ("active", "engaged", "hired", "expired", "erased")
OUTBOX_PORTS = ("hiredesk", "nomina360", "shiftgrid", "learnbite", "m365", "whatsapp")
OUTBOX_STATUSES = ("pending", "relaying", "api_confirmed", "csv_confirmed", "failed", "downgraded")


def _enum(name: str, values: tuple[str, ...]) -> Enum:
    return Enum(*values, name=name, native_enum=True, validate_strings=True)


BRAND_ENUM = _enum("brand_id", BRANDS)
LANGUAGE_ENUM = _enum("preferred_language", LANGUAGES)
SOURCE_ENUM = _enum("candidate_source", CANDIDATE_SOURCES)
STATE_ENUM = _enum("fs_state", STATES)  # one type shared by Candidate and Application
ROLE_ENUM = _enum("shift_role", ROLES)
OPEN_SHIFT_STATUS_ENUM = _enum("open_shift_status", OPEN_SHIFT_STATUSES)
CONSENT_CHANNEL_ENUM = _enum("consent_channel", CONSENT_CHANNELS)
CONSENT_PURPOSE_ENUM = _enum("consent_purpose", CONSENT_PURPOSES)
CONSENT_STATUS_ENUM = _enum("consent_status", CONSENT_STATUSES)
DECISION_TYPE_ENUM = _enum("decision_type", DECISION_TYPES)
ACTOR_TYPE_ENUM = _enum("actor_type", ACTOR_TYPES)
CONFIRMATION_STATUS_ENUM = _enum("confirmation_status", CONFIRMATION_STATUSES)
ROLE_ON_DAY1_ENUM = ROLE_ENUM  # same value set: till/foh fallbacks per C-L8
CURRENT_BLOCKER_ENUM = _enum("current_blocker", CURRENT_BLOCKERS)
BENCH_REASON_ENUM = _enum("bench_reason", BENCH_REASONS)
BENCH_STATUS_ENUM = _enum("bench_status", BENCH_STATUSES)
OUTBOX_PORT_ENUM = _enum("outbox_port", OUTBOX_PORTS)
OUTBOX_STATUS_ENUM = _enum("outbox_status", OUTBOX_STATUSES)


class Restaurant(Base):
    """Scope reference shared by everything else (data-model: Restaurant)."""

    __tablename__ = "restaurants"

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    # Identity mirrors HireDesk/ShiftGrid site codes (R001, R002, ...).
    code: Mapped[str] = mapped_column(String(16), unique=True)
    brand_id: Mapped[str] = mapped_column(BRAND_ENUM)
    name: Mapped[str] = mapped_column(String(120))
    city: Mapped[str] = mapped_column(String(80))
    timezone: Mapped[str] = mapped_column(String(40))
    bench_enabled: Mapped[bool] = mapped_column(Boolean)


class OpenShift(Base):
    """A concrete ShiftGrid shift a candidate can be matched to (ADR-002)."""

    __tablename__ = "open_shifts"

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    restaurant_id: Mapped[UUID] = mapped_column(ForeignKey("restaurants.id"))
    shiftgrid_shift_id: Mapped[str] = mapped_column(String(64), unique=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    role: Mapped[str] = mapped_column(ROLE_ENUM)
    requires_food_hygiene: Mapped[bool] = mapped_column(Boolean)  # C-L8
    status: Mapped[str] = mapped_column(OPEN_SHIFT_STATUS_ENUM, default="open")
    matched_application_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("applications.id", use_alter=True), nullable=True
    )


class Candidate(Base):
    """The person in conversation; FirstShift is the system of record."""

    __tablename__ = "candidates"

    # id is also the external ref for Nómina360 idempotency (C-T5)
    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    brand_id: Mapped[str] = mapped_column(BRAND_ENUM)
    first_name: Mapped[str] = mapped_column(String(80))  # no surname until Nómina360 needs it
    phone: Mapped[str] = mapped_column(String(32))
    preferred_language: Mapped[str] = mapped_column(LANGUAGE_ENUM)
    hiredesk_candidate_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    nomina360_employee_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state: Mapped[str] = mapped_column(STATE_ENUM, default="new")  # mirrored from Application
    source: Mapped[str] = mapped_column(SOURCE_ENUM)
    consent_status: Mapped[str | None] = mapped_column(
        CONSENT_STATUS_ENUM, nullable=True, default=None
    )  # derived from Consent rows
    erased_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # C-L5 erasure marker


class Application(Base):
    """One candidate x one open-shift opportunity, carrying the state machine."""

    __tablename__ = "applications"

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    candidate_id: Mapped[UUID] = mapped_column(ForeignKey("candidates.id"))
    restaurant_id: Mapped[UUID] = mapped_column(ForeignKey("restaurants.id"))
    # Postgres cannot FK into arrays; membership is enforced at the core.
    target_open_shift_ids: Mapped[list[UUID]] = mapped_column(ARRAY(Uuid()), default=list)
    requisition_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hiredesk_application_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state: Mapped[str] = mapped_column(STATE_ENUM, default="new")
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Consent(Base):
    """The record the DPO never had: timestamped consent with notice version (C-L1)."""

    __tablename__ = "consents"

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    candidate_id: Mapped[UUID] = mapped_column(ForeignKey("candidates.id"))
    channel: Mapped[str] = mapped_column(CONSENT_CHANNEL_ENUM)  # C-L2, per-channel consent
    purpose: Mapped[str] = mapped_column(CONSENT_PURPOSE_ENUM)
    notice_version: Mapped[str] = mapped_column(String(16))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The message that carried the consent; message ids live in the event
    # stream, so this is a reference without a hard FK until messages land.
    evidence_message_id: Mapped[UUID | None] = mapped_column(Uuid(), nullable=True)


class Decision(Base):
    """Every decision that significantly affects a candidate, with its named human (C-L6)."""

    __tablename__ = "decisions"

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    application_id: Mapped[UUID] = mapped_column(ForeignKey("applications.id"))
    type: Mapped[str] = mapped_column(DECISION_TYPE_ENUM)
    recommended_by: Mapped[str] = mapped_column(String(120))  # agent id, model, prompt version
    decided_by: Mapped[str] = mapped_column(
        String(120)
    )  # named human; guards in the core (INV-1/2)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # The facts the human saw; references an event or summary id.
    facts_seen: Mapped[UUID | None] = mapped_column(Uuid(), nullable=True)


class FirstShift(Base):
    """The scheduled first shift and commitment engine, with O11 tracking fields."""

    __tablename__ = "first_shifts"

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    application_id: Mapped[UUID] = mapped_column(ForeignKey("applications.id"))
    open_shift_id: Mapped[UUID] = mapped_column(ForeignKey("open_shifts.id"))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # >= 24 h ahead
    confirmation_status: Mapped[str] = mapped_column(CONFIRMATION_STATUS_ENUM, default="pending")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    backup_bench_entry_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("bench_entries.id", use_alter=True), nullable=True
    )
    backup_activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trainer_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    role_on_day1: Mapped[str | None] = mapped_column(
        ROLE_ON_DAY1_ENUM, nullable=True
    )  # till/foh if hygiene pending (C-L8)

    # O11 hired-to-rota tracking: the window between verbal yes and first
    # worked shift that no system owns today.
    promise_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    docs_complete_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    nomina360_write_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    nomina360_api_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # weak signal (C-T3)
    csv_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # strong signal (C-T4)
    rota_unlock_date: Mapped[date] = mapped_column(DATE())  # next Thursday lock (T-hugo-12)
    current_blocker: Mapped[str] = mapped_column(CURRENT_BLOCKER_ENUM, default="none")
    blocker_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ready_for_rota_signaled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # only after csv_confirmed_at or a recorded exception (O12 gate)


class BenchEntry(Base):
    """The formalized maybes pool (O4); re-engagement requires valid consent (ADR-005)."""

    __tablename__ = "bench_entries"

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    candidate_id: Mapped[UUID] = mapped_column(ForeignKey("candidates.id"))
    restaurant_id: Mapped[UUID] = mapped_column(ForeignKey("restaurants.id"))
    reason: Mapped[str] = mapped_column(BENCH_REASON_ENUM)
    consent_id: Mapped[UUID] = mapped_column(ForeignKey("consents.id"))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )  # consent expiry (C-L4)
    last_contacted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reengagement_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(BENCH_STATUS_ENUM, default="active")


class AuditEvent(Base):
    """Immutable, append-only (INV-5): who, what, when, why. Update and delete
    are blocked by database triggers created in the core migration."""

    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_type: Mapped[str] = mapped_column(ACTOR_TYPE_ENUM)
    actor_id: Mapped[str] = mapped_column(String(120))  # manager actions carry identity (C-L6)
    application_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("applications.id", use_alter=True), nullable=True
    )
    candidate_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("candidates.id", use_alter=True), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(64))
    state_from: Mapped[str | None] = mapped_column(String(40), nullable=True)
    state_to: Mapped[str | None] = mapped_column(String(40), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)  # typed details; never document contents
    idempotency_key: Mapped[str | None] = mapped_column(
        String(160), nullable=True
    )  # links to OutboxMessage (C-T6)


class OutboxMessage(Base):
    """Every outbound write to a client system (architecture rule 4, ADR-003)."""

    __tablename__ = "outbox_messages"

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    port: Mapped[str] = mapped_column(OUTBOX_PORT_ENUM)
    operation: Mapped[str] = mapped_column(String(64))  # e.g. create_employee, assign_shift
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)  # the validated Pydantic payload
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True)  # C-T5 scheme
    status: Mapped[str] = mapped_column(OUTBOX_STATUS_ENUM, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_entity_id: Mapped[UUID | None] = mapped_column(Uuid(), nullable=True)
