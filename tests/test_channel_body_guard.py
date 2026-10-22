"""F09 iteration-1, T1 (S3): the channel-body guard.

Spec source: odd/tasks/iteration-1.md T1/T2 and the observed defect in
evals/reports/calibration-v1-report.md: the fallback body
``f"Lumbre Burger: {template.replace('_', ' ')}"`` in
``app/sim/dispatch.py::_channel_message`` and
``app/services/scripted.py::ScriptedJourney._whatsapp_outbound`` leaks the raw
internal outbox identifier into candidate-facing text whenever a core outbox
kind has no configured body template (eval-p002 delivered
``Lumbre Burger: bench.reserve backup`` to the transcript).

The guard: a whitelist of candidate-facing templates with real human copy,
a separate set of internal-recipient kinds (trainer.notify,
bench.reserve_backup, backup.activate, anything routed to
manager-sim/hrbp-sim/trainer-sim/bench-backup-sim) that get their own safe
body, and no candidate-facing fallback identifier at all: an unknown kind
addressed to a candidate is never delivered as a message; it is recorded
(warning log, rule 7) and no pending outbound is returned.

RED contract: every test here that asserts the absence of the identifier
must fail against the current fallback before the guard is implemented.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.db.models import Candidate
from app.services.scripted import (
    _SCRIPTED_BODIES,
    CANDIDATE_FACING_TEMPLATES,
    ScriptedJourney,
)
from app.sim.dispatch import SIM_BODIES, _channel_message
from app.sim.store import RunRef

# Raw internal identifier fragments that must never appear in a body.
INTERNAL_MARKERS = (
    "bench.reserve",
    "bench_reserve",
    "trainer.notify",
    "trainer_notify",
    "backup.activate",
    "backup_activate",
    "some.unknown",
    "some_unknown",
)

FALLBACK_PREFIX = "Lumbre Burger: bench.reserve"


def make_candidate() -> Candidate:
    return Candidate(
        id=uuid4(),
        brand_id="lumbre",
        first_name="Vera",
        phone="+34600111222",
        preferred_language="es",
        source="qr",
        state="new",
    )


def make_run(candidate: Candidate) -> RunRef:
    return RunRef(
        id=uuid4(),
        trace_id="trc-body-guard",
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
        trace_id="trc-body-guard",
    )


def assert_no_internal_identifier(body: str) -> None:
    for marker in INTERNAL_MARKERS:
        assert marker not in body, f"body leaks internal identifier '{marker}': {body}"
    assert not body.startswith(FALLBACK_PREFIX), f"fallback leak: {body}"


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@contextmanager
def capture_warnings(logger_name: str) -> Iterator[_ListHandler]:
    """Capture warnings straight on the module logger: independent of root
    propagation and of the logger ``disabled`` flag that the celery import
    path leaves set by other test modules."""
    logger = logging.getLogger(logger_name)
    handler = _ListHandler()
    old_level, old_propagate, old_disabled = logger.level, logger.propagate, logger.disabled
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    logger.disabled = False
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
        logger.propagate = old_propagate
        logger.disabled = old_disabled


# --------------------------------------------------- sim dispatch path (F07)


def test_sim_internal_kinds_get_safe_bodies_without_identifiers() -> None:
    """bench.reserve_backup / trainer.notify / backup.activate reach internal
    sims with a human-readable body, never the raw outbox identifier."""
    candidate = make_candidate()
    run = make_run(candidate)
    expected_recipients = {
        "trainer.notify": "trainer-sim",
        "bench.reserve_backup": "bench-backup-sim",
        "backup.activate": "manager-sim",
    }
    for kind, recipient in expected_recipients.items():
        outbound = _channel_message(kind, {"application_id": "app-1"}, candidate, run)
        assert outbound is not None, kind
        assert outbound.message.recipient_ref == recipient, kind
        assert_no_internal_identifier(outbound.message.body)


def test_sim_unknown_kind_addressed_to_candidate_is_not_delivered(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An outbox kind with no configured copy is never rendered as
    candidate-facing text: no pending outbound, and the suppression stays
    observable (rule 7) through a warning log."""
    candidate = make_candidate()
    run = make_run(candidate)
    with capture_warnings("app.sim.dispatch") as records:
        outbound = _channel_message(
            "whatsapp.out", {"template": "some.unknown_kind"}, candidate, run
        )
    assert outbound is None
    assert any("some.unknown_kind" in message for message in records.messages)


# ------------------------------------------------- scripted journey path (F06)


def test_scripted_internal_kinds_get_safe_bodies_without_identifiers() -> None:
    candidate = make_candidate()
    journey = make_journey(candidate)
    expected_recipients = {
        "trainer.notify": "trainer-sim",
        "bench.reserve_backup": "bench-backup-sim",
    }
    for kind, recipient in expected_recipients.items():
        outbound = journey._whatsapp_outbound(kind, {"application_id": "app-1"}, candidate)
        assert outbound is not None, kind
        assert outbound.message.recipient_ref == recipient, kind
        assert_no_internal_identifier(outbound.message.body)


def test_scripted_unknown_kind_addressed_to_candidate_is_not_delivered(
    caplog: pytest.LogCaptureFixture,
) -> None:
    candidate = make_candidate()
    journey = make_journey(candidate)
    with capture_warnings("app.services.scripted") as records:
        outbound = journey._whatsapp_outbound(
            "whatsapp.out", {"template": "some.unknown_kind"}, candidate
        )
    assert outbound is None
    assert any("some.unknown_kind" in message for message in records.messages)


def test_scripted_manager_routed_unknown_kind_gets_safe_internal_body() -> None:
    """Internal recipients (manager-sim) keep receiving a message when the
    kind has no configured copy, but with the safe internal body."""
    candidate = make_candidate()
    journey = make_journey(candidate)
    outbound = journey._whatsapp_outbound(
        "whatsapp.out", {"to": "manager", "template": "some.manager_note"}, candidate
    )
    assert outbound is not None
    assert outbound.message.recipient_ref == "manager-sim"
    assert_no_internal_identifier(outbound.message.body)


# ------------------------------------------------------- whitelist invariants


def test_whitelist_templates_all_have_configured_copy() -> None:
    """Every candidate-facing whitelisted template resolves to real human
    copy in the dispatch body maps; the whitelist is never aspirational."""
    for template in CANDIDATE_FACING_TEMPLATES:
        body = (
            SIM_BODIES.get(template)
            or SIM_BODIES.get(template.replace(".", "_"))
            or _SCRIPTED_BODIES.get(template)
        )
        assert body is not None, f"whitelisted template without copy: {template}"


def test_whitelist_covers_every_candidate_facing_template() -> None:
    """The known candidate-facing templates are all whitelisted, so the guard
    and the copy stay in sync."""
    candidate_templates = {
        "offer",
        "rejection",
        "nudge_1",
        "nudge_2",
        "interview_reminder",
        "bench_offer",
        "bench_reengagement",
    }
    assert candidate_templates == set(CANDIDATE_FACING_TEMPLATES)


# ------------------------------------- PRESERVE: configured copy is unchanged


def test_sim_configured_templates_keep_their_exact_bodies() -> None:
    candidate = make_candidate()
    run = make_run(candidate)
    cases = [
        (
            "whatsapp.out",
            {"to": "manager", "template": "decision_reminder"},
            "manager-sim",
            SIM_BODIES["decision_reminder"],
        ),
        (
            "backup.activate",
            {"application_id": "app-1"},
            "manager-sim",
            SIM_BODIES["backup_activate"],
        ),
        (
            "whatsapp.out",
            {"to": "area_hrbp", "template": "decision_escalation"},
            "hrbp-sim",
            SIM_BODIES["decision_escalation"],
        ),
    ]
    for kind, payload, recipient, body in cases:
        outbound = _channel_message(kind, payload, candidate, run)
        assert outbound is not None, payload
        assert outbound.message.recipient_ref == recipient, payload
        assert outbound.message.body == body, payload


def test_scripted_configured_templates_keep_their_exact_bodies() -> None:
    candidate = make_candidate()
    journey = make_journey(candidate)
    cases = [
        ({"template": "offer"}, candidate.phone, _SCRIPTED_BODIES["offer"]),
        ({"template": "rejection"}, candidate.phone, _SCRIPTED_BODIES["rejection"]),
        (
            {"to": "manager", "template": "decision_request"},
            "manager-sim",
            _SCRIPTED_BODIES["decision_request"],
        ),
    ]
    for payload, recipient, body in cases:
        outbound = journey._whatsapp_outbound("whatsapp.out", payload, candidate)
        assert outbound is not None, payload
        assert outbound.message.recipient_ref == recipient, payload
        assert outbound.message.body == body, payload
