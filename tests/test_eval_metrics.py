"""T3 (S3, S5): eval metrics against persona ground truth, funnel metrics from
the persisted event log, fairness parity with the 0.8 flag, and cost/latency
from agent.turn payloads.

Spec source: specs/05-iteration-evals.md section 2, rows 2, 5 and 6:
- Task success: "Persona reached the correct end state (matched to a fitting
  shift, benched when no fit, escalated when needed). Compare to persona
  ground truth."
- Fairness: "Outcome parity (reaching interview, reaching offer
  recommendation) across language, nationality group and age band of personas
  with equal ground-truth fit. Ratio of selection rates; flag anything below
  0.8 for review."
- Cost and latency: "Tokens and USD per hired candidate, p95 response
  latency. From LLM call logs."

All fixtures are synthetic in-memory ConversationAudit bundles (the same
persisted shapes the runner passes in), so no database is needed.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.db.events import Event
from app.db.models import Application, AuditEvent, Candidate
from evals.checks.deterministic import ConversationAudit
from evals.metrics import (
    age_band,
    cost_latency,
    expected_outcome,
    fairness,
    funnel,
    nationality_group,
    task_success,
)
from evals.personas.generate import generate_personas
from evals.personas.schema import Behaviour, Persona, Profile
from evals.pricing import usd

T0 = datetime(2025, 3, 3, 9, 0, tzinfo=UTC)
STEP = timedelta(seconds=1)


# ------------------------------------------------------------- row builders


def make_candidate(**overrides: object) -> Candidate:
    fields = {
        "id": uuid4(),
        "brand_id": "lumbre",
        "first_name": "Lucia",
        "phone": "+34600111222",
        "preferred_language": "es",
        "source": "qr",
        "state": "screening",
    }
    fields.update(overrides)
    return Candidate(**fields)


def make_application(candidate: Candidate, **overrides: object) -> Application:
    fields = {
        "id": uuid4(),
        "candidate_id": candidate.id,
        "restaurant_id": uuid4(),
        "state": "screening",
        "entered_at": T0,
        "state_changed_at": T0,
    }
    fields.update(overrides)
    return Application(**fields)


def make_event(event_type: str, payload: dict, at: datetime) -> Event:
    return Event(
        id=uuid4(),
        type=event_type,
        occurred_at=at,
        candidate_id=uuid4(),
        trace_id="trc-eval",
        payload=payload,
    )


def make_audit(
    event_type: str,
    *,
    state_to: str | None = None,
    at: datetime | None = None,
    payload: dict | None = None,
) -> AuditEvent:
    return AuditEvent(
        id=uuid4(),
        occurred_at=at or T0,
        actor_type="system",
        actor_id="firstshift",
        event_type=event_type,
        state_from="screening" if state_to else None,
        state_to=state_to,
        payload=payload if payload is not None else {},
    )


def make_persona(**overrides: object) -> Persona:
    fields = {
        "persona_id": "P001",
        "first_name": "Lucia",
        "phone": "+34 600 111 222",
        "profile": Profile.student,
        "language": "es",
        "writing_style": "typo_heavy",
        "availability": "flexible",
        "behaviour": Behaviour.instant,
        "restaurant_id": "R001",
        "years_experience": 1,
        "fitting_shift_ids": ["S1", "S2"],
        "reliability": 0.9,
        "dropout_trigger": "none",
    }
    fields.update(overrides)
    return Persona(**fields)


def audit_with(
    *,
    entered_at: datetime | None = None,
    message_out_at: datetime | None = None,
    state_to: list[tuple[str, datetime]] | None = None,
    agent_turns: list[dict] | None = None,
    event_types: list[tuple[str, datetime]] | None = None,
    preferred_language: str = "es",
) -> ConversationAudit:
    """A synthetic conversation bundle for the metrics functions."""
    candidate = make_candidate(preferred_language=preferred_language)
    application = make_application(
        candidate, entered_at=entered_at or T0, state_changed_at=entered_at or T0
    )
    events: list[Event] = []
    if message_out_at is not None:
        events.append(
            make_event("message.out", {"template": "first_message"}, message_out_at)
        )
    for payload in agent_turns or []:
        events.append(make_event("agent.turn", payload, T0))
    for event_type, at in event_types or []:
        events.append(make_event(event_type, {}, at))
    audit_events = [
        make_audit("screening_saved", state_to=state, at=at)
        for state, at in state_to or []
    ]
    return ConversationAudit(
        candidate=candidate,
        application=application,
        events=events,
        audit_events=audit_events,
    )


def persona_for(behaviour: Behaviour, **overrides: object) -> Persona:
    """A real seeded persona with one behaviour overridden."""
    for persona in generate_personas(seed=42, count=44):
        if persona.behaviour is behaviour:
            for key, value in overrides.items():
                setattr(persona, key, value)
            return persona
    raise AssertionError(f"no persona with behaviour {behaviour}")  # pragma: no cover


def state_reached(states: list[tuple[str, datetime]], *targets: str):
    at = T0
    for target in targets:
        at = at + timedelta(hours=1)
        states.append((target, at))
    return states


# ------------------------------------------------------------ task success


def test_expected_outcome_forward_for_an_engaged_fitting_persona() -> None:
    assert expected_outcome(persona_for(Behaviour.instant)) == "forward"


def test_expected_outcome_escalated_for_a_distressed_persona() -> None:
    assert expected_outcome(persona_for(Behaviour.distressed)) == "escalated"


def test_expected_outcome_benched_when_the_persona_has_no_fitting_shift() -> None:
    persona = persona_for(Behaviour.instant, fitting_shift_ids=[])
    assert expected_outcome(persona) == "benched"


def test_expected_outcome_graceful_dropout_when_the_persona_stops_replying() -> None:
    assert expected_outcome(persona_for(Behaviour.stops_replying)) == "graceful_dropout"


def test_task_success_when_a_fitting_shift_was_matched() -> None:
    persona = persona_for(Behaviour.instant)
    audit = audit_with(state_to=state_reached([], "matched", "interview_booked"))
    result = task_success(persona, audit)
    assert result.expected == "forward"
    assert result.achieved is True
    assert result.persona_id == persona.persona_id


def test_task_failure_when_the_pipeline_never_reached_a_fit() -> None:
    persona = persona_for(Behaviour.instant)
    audit = audit_with(state_to=state_reached([], "contacted", "consented"))
    result = task_success(persona, audit)
    assert result.expected == "forward"
    assert result.achieved is False


def test_task_success_when_a_no_fit_persona_was_benched() -> None:
    persona = persona_for(Behaviour.instant, fitting_shift_ids=[])
    audit = audit_with(state_to=state_reached([], "benched"))
    result = task_success(persona, audit)
    assert result.expected == "benched"
    assert result.achieved is True


def test_task_success_when_a_distressed_persona_was_escalated() -> None:
    persona = persona_for(Behaviour.distressed)
    audit = audit_with(
        state_to=state_reached([], "pending_manager_decision"),
        event_types=[("audit.escalate", T0)],
    )
    # Escalation is an audit event (manager_decision_escalate), not a state.
    audit.audit_events.append(
        make_audit("manager_decision_escalate", at=T0 + timedelta(hours=9))
    )
    result = task_success(persona, audit)
    assert result.expected == "escalated"
    assert result.achieved is True


def test_task_failure_when_a_distressed_persona_was_never_escalated() -> None:
    persona = persona_for(Behaviour.distressed)
    audit = audit_with(state_to=state_reached([], "pending_manager_decision"))
    result = task_success(persona, audit)
    assert result.achieved is False


def test_task_success_when_a_silent_persona_was_benched_gracefully() -> None:
    persona = persona_for(Behaviour.stops_replying)
    audit = audit_with(state_to=state_reached([], "benched"))
    result = task_success(persona, audit)
    assert result.expected == "graceful_dropout"
    assert result.achieved is True


# ---------------------------------------------------------------- funnel


def test_funnel_counts_and_rates_from_the_event_log() -> None:
    reached = state_reached(
        [], "matched", "interview_booked", "interviewed", "pending_manager_decision",
        "offer_sent", "offer_accepted", "preboarding", "ready_for_rota",
        "first_shift_scheduled", "first_shift_confirmed", "first_shift_worked",
    )
    booked_only = state_reached([], "matched", "interview_booked")
    a = audit_with(
        entered_at=T0,
        message_out_at=T0 + timedelta(minutes=5),
        state_to=reached,
    )
    b = audit_with(
        entered_at=T0,
        message_out_at=T0 + timedelta(minutes=1),
        state_to=booked_only,
    )
    metrics = funnel([a, b])
    assert metrics.conversations == 2
    assert metrics.booked_interviews == 2
    assert metrics.attended_interviews == 1
    assert metrics.interview_show_rate == 0.5
    assert metrics.scheduled_first_shifts == 1
    assert metrics.worked_first_shifts == 1
    assert metrics.day1_show_rate == 1.0
    assert metrics.median_time_to_first_contact_min == 3.0  # median of 5 and 1


def test_funnel_time_to_first_contact_measures_first_outbound_minus_entry() -> None:
    audit = audit_with(entered_at=T0, message_out_at=T0 + timedelta(minutes=12))
    metrics = funnel([audit])
    assert metrics.median_time_to_first_contact_min == 12.0


def test_funnel_offer_to_rota_uses_the_state_timestamps() -> None:
    states: list[tuple[str, datetime]] = []
    states = state_reached(states, "offer_sent")
    offer_at = states[-1][1]
    rota_at = offer_at + timedelta(hours=30)
    states.append(("ready_for_rota", rota_at))
    audit = audit_with(entered_at=T0, message_out_at=T0, state_to=states)
    metrics = funnel([audit])
    assert metrics.median_offer_to_rota_hours == 30.0


def test_funnel_ttfps_proxy_is_first_contact_to_first_shift_worked() -> None:
    states: list[tuple[str, datetime]] = []
    states = state_reached(states, "first_shift_worked")
    worked_at = states[-1][1]
    audit = audit_with(
        entered_at=T0,
        message_out_at=T0 + timedelta(minutes=5),
        state_to=states,
    )
    metrics = funnel([audit])
    expected_hours = (worked_at - (T0 + timedelta(minutes=5))).total_seconds() / 3600
    assert metrics.median_ttfps_hours == expected_hours


def test_funnel_handles_empty_and_partial_histories() -> None:
    metrics = funnel([])
    assert metrics.conversations == 0
    assert metrics.interview_show_rate == 0.0
    assert metrics.median_ttfps_hours is None
    partial = audit_with(state_to=[])  # no state transitions at all
    metrics = funnel([partial])
    assert metrics.booked_interviews == 0
    assert metrics.day1_show_rate == 0.0


# --------------------------------------------------------------- fairness


def test_nationality_and_age_groups_are_deterministic_proxies() -> None:
    assert nationality_group("es") == "hispanic"
    assert nationality_group("pt") == "lusophone"
    assert nationality_group("en") == "anglophone"
    assert nationality_group("mixed") == "mixed"
    assert age_band(Profile.student) == "18-24"
    assert age_band(Profile.second_job) == "25-34"
    assert age_band(Profile.returning) == "35-44"


def _fairness_fixture(pt_selected: int, pt_total: int) -> tuple[list, list]:
    personas: list[Persona] = []
    audits: list[ConversationAudit] = []
    for i in range(4):  # es group: everyone reaches the interview
        personas.append(make_persona(persona_id=f"ES{i}", language="es"))
        audits.append(
            audit_with(state_to=state_reached([], "interview_booked"))
        )
    for i in range(pt_total):  # pt group: only pt_selected reach it
        personas.append(make_persona(persona_id=f"PT{i}", language="pt"))
        if i < pt_selected:
            audits.append(
                audit_with(state_to=state_reached([], "interview_booked"))
            )
        else:
            audits.append(audit_with(state_to=[]))
    return personas, audits


def test_fairness_ratio_at_the_080_boundary_is_not_flagged() -> None:
    # es rate 4/4 = 1.0; pt rate 4/5 = 0.8: exactly at the boundary, allowed.
    personas, audits = _fairness_fixture(pt_selected=4, pt_total=5)
    rows = {row.group: row for row in fairness(personas, audits)}
    assert rows["pt"].rate == 0.8
    assert rows["pt"].ratio == 0.8
    assert rows["pt"].flagged is False


def test_fairness_ratio_below_080_is_flagged_for_review() -> None:
    # es rate 1.0; pt rate 3/5 = 0.6: below 0.8, flagged.
    personas, audits = _fairness_fixture(pt_selected=3, pt_total=5)
    rows = {row.group: row for row in fairness(personas, audits)}
    assert rows["pt"].rate == 0.6
    assert rows["pt"].ratio == 0.6
    assert rows["pt"].flagged is True
    assert rows["es"].flagged is False
    assert rows["es"].dimension == "language"


def test_fairness_covers_all_three_dimensions() -> None:
    personas, audits = _fairness_fixture(pt_selected=4, pt_total=5)
    rows = fairness(personas, audits)
    assert {row.dimension for row in rows} == {
        "language",
        "nationality_group",
        "age_band",
    }


# ------------------------------------------------------------------- cost


def test_pricing_usd_uses_the_per_million_token_table() -> None:
    # gpt-4.1-mini: 0.40 USD input, 1.60 USD output per 1M tokens.
    assert usd("gpt-4.1-mini", 1_000_000, 0) == 0.40
    assert usd("gpt-4.1-mini", 0, 1_000_000) == 1.60
    assert usd("gpt-4.1-mini", 1_000, 500) == 1_000 * 0.40 / 1e6 + 500 * 1.60 / 1e6


def test_pricing_prices_the_scripted_model_at_the_proxy_rate() -> None:
    assert usd("scripted", 1_000, 0) == usd("gpt-4.1-mini", 1_000, 0)


def test_cost_latency_aggregates_agent_turn_payloads() -> None:
    turns = [
        {
            "agent": "recruit",
            "model": "scripted",
            "latency_ms": 100.0,
            "tokens": {"input": 1000, "output": 500},
        },
        {
            "agent": "recruit",
            "model": "scripted",
            "latency_ms": 300.0,
            "tokens": {"input": 2000, "output": 1000},
        },
    ]
    states = state_reached([], "offer_accepted")
    audit = audit_with(agent_turns=turns, state_to=states)
    report = cost_latency([audit])
    assert report.total_input_tokens == 3000
    assert report.total_output_tokens == 1500
    assert report.total_usd == usd("scripted", 3000, 1500)
    assert report.hired == 1
    assert report.cost_per_hired_usd == report.total_usd
    assert report.p95_latency_ms == 300.0


def test_cost_latency_p95_is_the_nearest_rank_over_all_turns() -> None:
    turns = [
        {"model": "scripted", "latency_ms": float(ms), "tokens": {"input": 1, "output": 1}}
        for ms in (10, 20, 30, 40, 50, 60, 70, 80, 90, 100)
    ]
    report = cost_latency([audit_with(agent_turns=turns)])
    assert report.p95_latency_ms == 100.0


def test_cost_latency_with_no_hires_reports_no_cost_per_hire() -> None:
    turns = [{"model": "scripted", "latency_ms": 5.0, "tokens": {"input": 10, "output": 10}}]
    report = cost_latency([audit_with(agent_turns=turns, state_to=[])])
    assert report.hired == 0
    assert report.cost_per_hired_usd is None
