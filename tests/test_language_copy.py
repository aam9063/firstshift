"""F10 iteration-2 (T1/T2, S3/S2): language-aware candidate-facing copy.

Spec source: odd/tasks/iteration-2.md (the single change) and
specs/05-iteration-evals.md section 4. Observed gap: the seven
candidate-facing templates lived only in Spanish in both dispatch
dictionaries (eval-p002 opens in Spanish, switches to Portuguese, then
receives the offer in Spanish again), and the core snapshot language was
hardcoded to "es" in evals/run.py, so the language guardrail
(``outbound_language_matches``) passed without measuring anything for
Portuguese and English candidates.

RED contract: the copy tests assert the per-language bodies and must fail
against the Spanish-only dictionaries; the guardrail tests build the
conversation shape the pre-fix dispatch produces (a Spanish offer body with
no language tag, addressed to a Portuguese candidate) and must see the
guardrail report a violation once the instrumentation is non-vacuous.

The expected copy below is the spec of the authored variants: WhatsApp-sized,
equivalent in meaning to the Spanish originals, no new promises, no tone
shift. Internal-recipient bodies from iteration-1 are not candidate-facing
and must stay exactly as they are.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.db.events import Event
from app.db.models import Application, Candidate
from app.services.scripted import (
    _SCRIPTED_BODIES,
    CANDIDATE_FACING_TEMPLATES,
    ScriptedJourney,
)
from app.sim.dispatch import SIM_BODIES, _channel_message
from app.sim.store import RunRef
from evals.checks.deterministic import (
    ConversationAudit,
    check_outbound_language_matches,
)

T0 = datetime(2025, 3, 3, 9, 0, tzinfo=UTC)
STEP = timedelta(seconds=1)

# Authored per-language variants of the seven candidate-facing templates.
EXPECTED_BODIES: dict[str, dict[str, str]] = {
    "pt": {
        "offer": "Oferta de emprego da Lumbre Burger: responde SIM para aceitar.",
        "nudge_1": "Continuamos com a tua candidatura? Responde para continuar.",
        "nudge_2": "A tua candidatura continua aberta: responde para continuar.",
        "interview_reminder": "Lembrete da tua entrevista na Lumbre Burger.",
        "bench_reengagement": "Temos uma nova vaga para ti na Lumbre Burger.",
        "bench_offer": "Queres ficar na nossa bolsa de emprego?",
        "rejection": "Obrigado pelo teu interesse: nesta ocasião não continuamos.",
    },
    "en": {
        "offer": "Job offer from Lumbre Burger: reply YES to accept.",
        "nudge_1": "Shall we continue with your application? Reply to keep going.",
        "nudge_2": "Your application is still open: reply to keep going.",
        "interview_reminder": "Reminder of your interview at Lumbre Burger.",
        "bench_reengagement": "We have a new vacancy for you at Lumbre Burger.",
        "bench_offer": "Would you like to stay in our talent pool?",
        "rejection": "Thank you for your interest: this time we will not move forward.",
    },
}


# --------------------------------------------------------------- row builders


def make_candidate(preferred_language: str | None = "es") -> Candidate:
    return Candidate(
        id=uuid4(),
        brand_id="lumbre",
        first_name="Vera",
        phone="+34600111222",
        preferred_language=preferred_language,  # type: ignore[arg-type]
        source="qr",
        state="new",
    )


def make_run(candidate: Candidate) -> RunRef:
    return RunRef(
        id=uuid4(),
        trace_id="trc-language-copy",
        candidate_id=candidate.id,
        application_id=uuid4(),
        manager_id="mgr-yolanda-001",
        manager_name="Yolanda",
        base_at=datetime.now(UTC),
        snapshot_json=None,
    )


def make_journey(candidate: Candidate) -> ScriptedJourney:
    # The unit under test only reads self._trace_id; no engine is touched.
    return ScriptedJourney(
        None,  # type: ignore[arg-type]
        application_id=uuid4(),
        candidate_id=candidate.id,
        trace_id="trc-language-copy",
    )


def make_application(candidate: Candidate) -> Application:
    return Application(
        id=uuid4(),
        candidate_id=candidate.id,
        restaurant_id=uuid4(),
        state="screening",
        entered_at=T0,
        state_changed_at=T0,
    )


def make_event(event_type: str, payload: dict, at: datetime) -> Event:
    return Event(
        id=uuid4(),
        type=event_type,
        occurred_at=at,
        candidate_id=uuid4(),
        trace_id="trc-language-copy",
        payload=payload,
    )


def make_audit(
    candidate: Candidate, application: Application, events: list[Event]
) -> ConversationAudit:
    return ConversationAudit(
        candidate=candidate,
        application=application,
        events=events,
        audit_events=[],
        consents=[],
        decisions=[],
    )


# --------------------------------- T1: per-language copy, scripted path (F06)


@pytest.mark.parametrize("candidate_language", ["pt", "en"])
def test_scripted_path_renders_candidate_templates_in_the_stated_language(
    candidate_language: str,
) -> None:
    candidate = make_candidate(candidate_language)
    journey = make_journey(candidate)
    for template in sorted(CANDIDATE_FACING_TEMPLATES):
        outbound = journey._whatsapp_outbound(
            "whatsapp.out", {"template": template}, candidate
        )
        assert outbound is not None, template
        assert outbound.message.body == EXPECTED_BODIES[candidate_language][template], (
            f"scripted path, template '{template}': expected the "
            f"{candidate_language} variant, got {outbound.message.body!r}"
        )
        assert getattr(outbound, "language", None) == candidate_language, template


# ------------------------------------ T1: per-language copy, sim path (F07)


@pytest.mark.parametrize("candidate_language", ["pt", "en"])
def test_sim_path_renders_candidate_templates_in_the_stated_language(
    candidate_language: str,
) -> None:
    candidate = make_candidate(candidate_language)
    run = make_run(candidate)
    for template in sorted(CANDIDATE_FACING_TEMPLATES):
        outbound = _channel_message("whatsapp.out", {"template": template}, candidate, run)
        assert outbound is not None, template
        assert outbound.message.body == EXPECTED_BODIES[candidate_language][template], (
            f"sim path, template '{template}': expected the "
            f"{candidate_language} variant, got {outbound.message.body!r}"
        )
        assert getattr(outbound, "language", None) == candidate_language, template


# ------------------------------------- T1: Spanish last-resort fallback (C-O4)


@pytest.mark.parametrize("unknown_language", ["fr", None])
def test_unknown_language_falls_back_to_the_spanish_original(
    unknown_language: str | None,
) -> None:
    candidate = make_candidate(unknown_language)
    journey = make_journey(candidate)
    run = make_run(candidate)
    for template in sorted(CANDIDATE_FACING_TEMPLATES):
        scripted = journey._whatsapp_outbound(
            "whatsapp.out", {"template": template}, candidate
        )
        assert scripted is not None, template
        assert scripted.message.body == _SCRIPTED_BODIES[template], template
        assert getattr(scripted, "language", None) == "es", template
        sim = _channel_message("whatsapp.out", {"template": template}, candidate, run)
        assert sim is not None, template
        assert sim.message.body == _SCRIPTED_BODIES[template], template
        assert getattr(sim, "language", None) == "es", template


# ------------------- PRESERVE: iteration-1 internal-recipient bodies unchanged


def test_internal_recipient_bodies_stay_unchanged_for_a_portuguese_candidate() -> None:
    """Internal-recipient copy is not candidate-facing (iteration-1): a
    Portuguese candidate must not change it, and it carries no candidate
    language tag."""
    candidate = make_candidate("pt")
    journey = make_journey(candidate)
    run = make_run(candidate)

    scripted = journey._whatsapp_outbound(
        "whatsapp.out", {"to": "manager", "template": "decision_request"}, candidate
    )
    assert scripted is not None
    assert scripted.message.recipient_ref == "manager-sim"
    assert scripted.message.body == _SCRIPTED_BODIES["decision_request"]
    assert getattr(scripted, "language", None) is None

    sim_cases = [
        (
            _channel_message(
                "whatsapp.out",
                {"to": "manager", "template": "decision_reminder"},
                candidate,
                run,
            ),
            SIM_BODIES["decision_reminder"],
        ),
        (
            _channel_message("backup.activate", {"application_id": "app-1"}, candidate, run),
            SIM_BODIES["backup_activate"],
        ),
    ]
    for outbound, expected in sim_cases:
        assert outbound is not None
        assert outbound.message.body == expected
        assert getattr(outbound, "language", None) is None


# --------------------------------- T2: the language guardrail is non-vacuous


def test_language_guardrail_reports_violation_for_untagged_spanish_body() -> None:
    """RED guardrail test: the conversation shape the pre-fix dispatch
    produces for a Portuguese candidate. The Spanish offer body carries no
    language tag, so the pre-fix check skips it and passes without measuring
    anything; the non-vacuous guardrail must report a violation."""
    candidate = make_candidate("pt")
    application = make_application(candidate)
    events = [
        make_event("message.in", {"text": "ola, quero saber mais"}, T0),
        make_event(
            "message.out",
            {"template": "agent_reply", "body": "Claro! Diga-me.", "language": "pt"},
            T0 + STEP,
        ),
        # Today's dispatch shape: candidate-facing body, no language tag.
        make_event(
            "message.out",
            {
                "template": "offer",
                "recipient_ref": candidate.phone,
                "body": _SCRIPTED_BODIES["offer"],
            },
            T0 + 2 * STEP,
        ),
    ]
    result = check_outbound_language_matches(make_audit(candidate, application, events))
    assert result.name == "outbound_language_matches"
    assert not result.passed, (
        "the language guardrail passed on a Spanish offer body sent to a "
        "Portuguese candidate: it is vacuous"
    )
    assert "offer" in result.evidence or "language tag" in result.evidence


def test_language_guardrail_flags_a_mismatched_tag_after_the_candidate_spoke() -> None:
    candidate = make_candidate("pt")
    application = make_application(candidate)
    events = [
        make_event("message.in", {"text": "ola, quero saber mais"}, T0),
        make_event(
            "message.out",
            {
                "template": "offer",
                "recipient_ref": candidate.phone,
                "body": _SCRIPTED_BODIES["offer"],
                "language": "es",
            },
            T0 + STEP,
        ),
    ]
    result = check_outbound_language_matches(make_audit(candidate, application, events))
    assert not result.passed
    assert "es" in result.evidence and "pt" in result.evidence


def test_language_guardrail_tolerates_the_intake_default_before_the_candidate_spoke() -> None:
    """A nudge fired while the candidate had not yet spoken uses the intake
    default (es); the preference is not yet stated, so the message cannot
    contradict it. The guardrail enforces the stated language from the first
    candidate inbound message onward."""
    candidate = make_candidate("pt")
    application = make_application(candidate)
    events = [
        make_event(
            "message.out",
            {
                "template": "nudge_1",
                "recipient_ref": candidate.phone,
                "body": _SCRIPTED_BODIES["nudge_1"],
                "language": "es",
            },
            T0,
        ),
        make_event("message.in", {"text": "ola, quero saber mais"}, T0 + STEP),
        make_event(
            "message.out",
            {"template": "agent_reply", "body": "Claro! Diga-me.", "language": "pt"},
            T0 + 2 * STEP,
        ),
    ]
    result = check_outbound_language_matches(make_audit(candidate, application, events))
    assert result.passed, result.evidence


def test_language_guardrail_passes_on_matching_tags_after_the_candidate_spoke() -> None:
    candidate = make_candidate("pt")
    application = make_application(candidate)
    events = [
        make_event("message.in", {"text": "ola, quero saber mais"}, T0),
        make_event(
            "message.out",
            {
                "template": "offer",
                "recipient_ref": candidate.phone,
                "body": EXPECTED_BODIES["pt"]["offer"],
                "language": "pt",
            },
            T0 + STEP,
        ),
    ]
    result = check_outbound_language_matches(make_audit(candidate, application, events))
    assert result.passed, result.evidence


def test_language_guardrail_skips_internal_recipient_bodies() -> None:
    """Messages to internal roles (trainer, bench backup, manager) are not
    part of the candidate's conversation: no language tag is required."""
    candidate = make_candidate("pt")
    application = make_application(candidate)
    events = [
        make_event("message.in", {"text": "ola, quero saber mais"}, T0),
        make_event(
            "message.out",
            {
                "template": "trainer.notify",
                "recipient_ref": "trainer-sim",
                "body": "Aviso interno del sistema de contratacion: revisa el panel.",
            },
            T0 + STEP,
        ),
        make_event(
            "message.out",
            {"template": "agent_reply", "body": "Claro! Diga-me.", "language": "pt"},
            T0 + 2 * STEP,
        ),
    ]
    result = check_outbound_language_matches(make_audit(candidate, application, events))
    assert result.passed, result.evidence
