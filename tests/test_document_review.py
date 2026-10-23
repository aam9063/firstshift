"""Third-party document hold (F11 T4/S4): the red-team fix for the
third_party_documents case.

Spec source: design/guardrails.md and design/state-machine.md row 21; the
red-team report (evals/reports/redteam-v1.md) recorded the gap: "documents of
someone else were silently accepted: the tracker completed to ready_for_rota
after the disclosure with no review record".

Designed behavior under test, driven through the REAL pipeline (the same
evals.run helpers the red-team suite uses):
- a candidate message claiming the submitted documents belong to another
  person is classified deterministically (app/core/inbound.py, no model call),
  sets an explicit review flag on the application record (boolean
  document_review_required plus document_review_cleared_at, with migration),
  appends a "documents_flagged_for_review" audit row and sends a canned
  notification from the message catalog that the documents need human review,
- the transition to ready_for_rota (row 21) then REQUIRES an explicit People
  Ops clearance: while the flag is set and uncleared, tracker_completed is
  rejected by the core guard and the tracker holds,
- the People Ops clearance function (app.sim.dispatch.clear_document_review)
  records the named human clearance, after which the tracker completes,
- a candidate whose documents are their own with no flag still reaches
  ready_for_rota (non-vacuity).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from evals.redteam import (
    THIRD_PARTY_DOCUMENTS,
    _drive,
    _persona,
)


@pytest.fixture(scope="module")
def sim_engine():
    from tests.test_sim_common import fresh_sim_engine

    generator = fresh_sim_engine()
    engine = next(generator)
    try:
        yield engine
    finally:
        generator.close()


@pytest.fixture(scope="module", autouse=True)
def seeded_world(sim_engine):
    """The same seeded world the red-team suite runs against (restaurants
    plus the seeded open shifts), so applications enter the real webhook."""
    from evals.run import _ensure_seed

    _ensure_seed(sim_engine, 42)
    return sim_engine


OWN_DOCUMENTS_TEXT = "Ya he subido todos mis documentos, los mios, sin problema."
DOCUMENT_REVIEW_FLAG = "documents_flagged_for_review"
DOCUMENT_REVIEW_TEMPLATE = "document_review"


def _catalog_bodies() -> frozenset[str]:
    from app.services.scripted import _CANDIDATE_BODIES, _SCRIPTED_BODIES

    return frozenset(
        body for variants in _CANDIDATE_BODIES.values() for body in variants.values()
    ) | frozenset(_SCRIPTED_BODIES.values())


def _application_row(engine, run):
    from sqlalchemy import select

    from app.db.models import Application

    with Session(engine) as session:
        row = session.scalars(
            select(Application).where(Application.id == run.application_id)
        ).one()
        session.expunge(row)
        return row


def _audit_types(engine, run) -> set[str]:
    from sqlalchemy import select

    from app.db.models import AuditEvent

    with Session(engine) as session:
        rows = session.scalars(
            select(AuditEvent).where(AuditEvent.candidate_id == run.candidate_id)
        ).all()
        return {row.event_type for row in rows}


def _outbound_bodies(engine, run) -> list[str]:
    from sqlalchemy import select

    from app.db.events import Event

    with Session(engine) as session:
        rows = session.scalars(
            select(Event).where(
                Event.trace_id == run.trace_id, Event.type == "message.out"
            )
        ).all()
        return [str(row.payload.get("body", "")) for row in rows]


# ------------------------------------------------------- the hold and the flag


def test_third_party_disclosure_sets_the_review_flag_and_audits_it(sim_engine) -> None:
    """The disclosure is classified deterministically, the record is flagged
    for human review and the candidate is told, from the catalog."""
    from evals.run import _current_state

    driven = _drive(
        sim_engine, _persona("GD-DOC-01", "Sergio", "+34 601 201 101"),
        ["Hola", "Sí", "Sí", "Sí", "Sí", "Sí", THIRD_PARTY_DOCUMENTS],
        world=True, stop_states=frozenset({"preboarding"}),
    )
    assert _current_state(sim_engine, driven.run) == "preboarding"

    row = _application_row(sim_engine, driven.run)
    assert row.document_review_required is True, (
        "the third-party disclosure did not set the explicit review flag"
    )
    assert row.document_review_cleared_at is None

    assert DOCUMENT_REVIEW_FLAG in _audit_types(sim_engine, driven.run), (
        "no documents_flagged_for_review audit row after the disclosure"
    )
    canned = [
        body for body in _outbound_bodies(sim_engine, driven.run)
        if body in _catalog_bodies()
    ]
    assert canned, (
        "no canned catalog notification that the documents need human review"
    )


def test_tracker_completion_is_held_until_people_ops_clearance(sim_engine) -> None:
    """Row 21 guard: with the flag set and uncleared, tracker_completed is
    rejected (the tracker holds); the named People Ops clearance lets the
    tracker complete afterwards."""
    from app.core.state_machine import ActorKind
    from app.sim.dispatch import SimDispatchRejected, clear_document_review
    from evals.run import _current_state, _dispatch, _sim_now

    driven = _drive(
        sim_engine, _persona("GD-DOC-02", "Sergio", "+34 601 201 102"),
        ["Hola", "Sí", "Sí", "Sí", "Sí", "Sí", THIRD_PARTY_DOCUMENTS],
        world=True, stop_states=frozenset({"preboarding"}),
    )
    with pytest.raises(SimDispatchRejected):
        _dispatch(
            sim_engine, driven.run, event="tracker_completed", role=ActorKind.SYSTEM,
            snapshot_updates={"documents_complete": True, "csv_confirmed": True},
        )
    assert _current_state(sim_engine, driven.run) == "preboarding", (
        "the held tracker must not leave preboarding without clearance"
    )

    clear_document_review(
        sim_engine, driven.run.application_id,
        cleared_by="People Ops: Marta", at=_sim_now(sim_engine, driven.run),
    )
    _dispatch(
        sim_engine, driven.run, event="tracker_completed", role=ActorKind.SYSTEM,
        snapshot_updates={"documents_complete": True, "csv_confirmed": True},
    )
    assert _current_state(sim_engine, driven.run) == "ready_for_rota"


# ------------------------------------------------------------ non-vacuity


def test_own_documents_with_no_flag_still_reach_ready_for_rota(sim_engine) -> None:
    """A candidate whose documents are their own with no disclosure is never
    held: the tracker completes exactly as before."""
    from app.core.state_machine import ActorKind
    from evals.run import _current_state, _dispatch

    driven = _drive(
        sim_engine, _persona("GD-OWN-03", "Lucía", "+34 601 201 103"),
        ["Hola", "Sí", "Sí", "Sí", "Sí", "Sí", OWN_DOCUMENTS_TEXT],
        world=True, stop_states=frozenset({"preboarding"}),
    )
    row = _application_row(sim_engine, driven.run)
    assert row.document_review_required is False, (
        "an ordinary documents message flagged the record for review"
    )
    _dispatch(
        sim_engine, driven.run, event="tracker_completed", role=ActorKind.SYSTEM,
        snapshot_updates={"documents_complete": True, "csv_confirmed": True},
    )
    assert _current_state(sim_engine, driven.run) == "ready_for_rota"


def test_clearance_records_the_named_human_and_timestamp(sim_engine) -> None:
    """The People Ops clearance function stores who cleared and when, and is
    the only way the flag releases the tracker."""
    from app.sim.dispatch import clear_document_review
    from evals.run import _sim_now

    driven = _drive(
        sim_engine, _persona("GD-CLR-04", "Sergio", "+34 601 201 104"),
        ["Hola", "Sí", "Sí", "Sí", "Sí", "Sí", THIRD_PARTY_DOCUMENTS],
        world=True, stop_states=frozenset({"preboarding"}),
    )
    cleared_at = datetime(2026, 10, 24, 9, 30, tzinfo=UTC)
    clear_document_review(
        sim_engine, driven.run.application_id,
        cleared_by="People Ops: Raul", at=cleared_at,
    )
    row = _application_row(sim_engine, driven.run)
    assert row.document_review_cleared_at == cleared_at
    assert _sim_now(sim_engine, driven.run) is not None  # run clock untouched


# ------------------------------------------------- the pure classifier itself


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (THIRD_PARTY_DOCUMENTS, True),
        ("Los documentos son los de mi hermana, los míos los perdí", True),
        ("Enviei os documentos do meu irmão, servem?", True),
        ("I uploaded my brother's documents because I lost mine", True),
        (OWN_DOCUMENTS_TEXT, False),
        ("Subo hoy mis documentos, ¿vale?", False),
        ("I will upload my documents tomorrow", False),
    ],
)
def test_third_party_document_flag_is_a_pure_keyword_check(
    text: str, expected: bool
) -> None:
    from app.core.inbound import flags_third_party_documents

    assert flags_third_party_documents(text) == expected
