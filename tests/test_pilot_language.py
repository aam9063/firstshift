"""Regression (F11 T2/S2): the pilot must reach 0 deterministic failures.

P029 (distressed, pt) failed ``outbound_language_matches``: the candidate was
created with the intake default ``preferred_language='es'`` and the canned G5
escalation reply to the candidate's first inbound was composed and tagged
``'es'`` two microseconds after that inbound, before ``save_language_tag``
could record the stated preference. The fix at the right layer: the HireDesk
intake carries the language source of truth (``HireDeskNewApplication.language``,
Spanish by default when nothing states otherwise), and the eval intake passes
the persona's language.

Pinned ordering rule (C-O4): no candidate-facing outbound sent after the
candidate's first inbound may carry a language tag different from the
candidate's stated preference.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.adapters.simulator import channel as simulator_channel
from app.api.webhooks import HireDeskNewApplication, hiredesk_webhook
from app.services.scripted import INTERNAL_RECIPIENT_REFS
from evals.checks.deterministic import (
    _first_candidate_inbound_at,
    run_deterministic_checks,
)
from evals.personas.generate import generate_personas
from evals.personas.schema import Behaviour, Persona
from evals.run import _ensure_seed, drive_conversation
from tests.test_sim_common import fresh_sim_engine


@pytest.fixture()
def sim_engine() -> Iterator[Engine]:
    """A throwaway migrated schema with the seeded pilot world."""
    generator = fresh_sim_engine()
    engine = next(generator)
    try:
        _ensure_seed(engine, 42)
        simulator_channel.sent.clear()
        yield engine
    finally:
        generator.close()


def _distressed_pt_persona() -> Persona:
    """The deterministic regression fixture: a distressed Portuguese-speaking
    persona, the exact class that tripped P029 (the canned G5 escalation
    reply fires on the first inbound, before any save_language_tag)."""
    personas = generate_personas(seed=42, count=30)
    matches = [
        p
        for p in personas
        if p.behaviour is Behaviour.distressed and p.language.value == "pt"
    ]
    assert matches, "the seeded bundle must contain a distressed pt persona"
    persona = matches[0]
    return persona.model_copy(update={"restaurant_id": "R001"})


def test_no_candidate_facing_outbound_after_first_inbound_contradicts_stated_language(
    sim_engine: Engine,
) -> None:
    """The ordering rule: after the candidate's first inbound, every
    candidate-facing outbound is tagged with the stated preference."""
    persona = _distressed_pt_persona()
    conversation = drive_conversation(sim_engine, persona)
    audit = conversation["audit"]

    # The deterministic check the pilot gates on must pass.
    results = run_deterministic_checks(audit)
    language_check = next(c for c in results if c.name == "outbound_language_matches")
    assert language_check.passed, language_check.evidence

    # And the rule holds directly (the check is not passed vacuously).
    stated_at = _first_candidate_inbound_at(audit.events)
    assert stated_at is not None, "the persona speaks, so a first inbound exists"
    after = [
        event
        for event in audit.events
        if event.type == "message.out"
        and event.payload.get("body")
        and event.payload.get("recipient_ref") not in INTERNAL_RECIPIENT_REFS
        and event.occurred_at > stated_at
    ]
    assert after, "non-vacuous: candidate-facing outbounds exist after the first inbound"
    for event in after:
        assert event.payload.get("language") == audit.candidate.preferred_language, (
            f"outbound at {event.occurred_at} (template "
            f"{event.payload.get('template')!r}) is tagged "
            f"{event.payload.get('language')!r} but the stated preference is "
            f"{audit.candidate.preferred_language!r}"
        )

    # The exact trigger of the P029 failure: the canned escalation reply to
    # the first inbound, composed from the intake source of truth.
    escalation = [e for e in after if e.payload.get("template") == "escalation"]
    assert escalation, "non-vacuous: a canned escalation reply exists"
    assert audit.candidate.preferred_language == "pt"
    assert escalation[0].payload.get("language") == "pt"


def test_intake_without_language_defaults_to_es(sim_engine: Engine) -> None:
    """Product behaviour preserved: a real HireDesk delivery that states no
    language creates the candidate with the Spanish intake default."""
    with Session(sim_engine) as session, session.begin():
        created = hiredesk_webhook(
            payload=HireDeskNewApplication(
                event="new_application",
                event_id=f"eval-lang-{uuid4().hex[:8]}",
                application_id=f"hd-lang-{uuid4().hex[:8]}",
                candidate_id=f"hdc-lang-{uuid4().hex[:8]}",
                restaurant_id="R001",
                first_name="Lucia",
                phone="+34600111222",
            ),
            session=session,
        )
        from app.db.models import Candidate

        candidate = session.get(Candidate, __import__("uuid").UUID(created["candidate_id"]))
        assert candidate is not None
        assert candidate.preferred_language == "es"


def test_intake_carrying_a_stated_language_sets_the_source_of_truth(
    sim_engine: Engine,
) -> None:
    """When the intake states the language, the candidate record carries it
    from creation, so every later composition (timers, canned replies) uses
    it instead of waiting for save_language_tag."""
    with Session(sim_engine) as session, session.begin():
        created = hiredesk_webhook(
            payload=HireDeskNewApplication(
                event="new_application",
                event_id=f"eval-lang-{uuid4().hex[:8]}",
                application_id=f"hd-lang-{uuid4().hex[:8]}",
                candidate_id=f"hdc-lang-{uuid4().hex[:8]}",
                restaurant_id="R001",
                first_name="Noelia",
                phone="+34600111223",
                language="pt",
            ),
            session=session,
        )
        from app.db.models import Candidate

        candidate = session.get(Candidate, __import__("uuid").UUID(created["candidate_id"]))
        assert candidate is not None
        assert candidate.preferred_language == "pt"
