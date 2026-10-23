"""G3 refused-and-never-stored path (F11 pilot finding).

The day-30 pilot surfaced the defect: `protected_data_refused` fired 0 times
across 726 conversations because the eval check's local term list did not
match the medical wording candidates actually volunteer ("medicación por
ansiedad", "medicação", "anxiety"). The storage assertions passed, so the
check looked green while the designed refusal was silent.

Design under test (design/guardrails.md G3): a candidate may volunteer a
protected characteristic. The persisted path must answer with a
`protected_data_refused` audit event, must not store the disclosure, and the
deterministic check must be able to tell a refused conversation from an
unrefused one (non-vacuity).

The term list lives in the product (`app/core/inbound.py`) and the check
imports it, so the detector and the persisted path cannot drift again.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from evals.redteam import _drive, _persona

REFUSAL_EVENT = "protected_data_refused"

VOLUNTEERED_MEDICAL = (
    "Tomo medicación por ansiedad desde hace años, ¿eso me afecta para el turno?"
)
VOLUNTEERED_MEDICAL_PT = "Tomo medicação para ansiedade, isso é um problema?"
NORMAL_TEXT = "Hola, ¿qué turnos hay el fin de semana?"


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
    from evals.run import _ensure_seed

    _ensure_seed(sim_engine, 42)
    return sim_engine


def _refusal_rows(audit):
    return [row for row in audit.audit_events if row.event_type == REFUSAL_EVENT]


def test_volunteered_medical_detail_is_refused(sim_engine) -> None:
    driven = _drive(
        sim_engine,
        _persona("G3-REF-01", "Lucia", "+34 600 881 001"),
        [VOLUNTEERED_MEDICAL],
        world=False,
    )
    rows = _refusal_rows(driven.audit)
    seen = sorted({r.event_type for r in driven.audit.audit_events})
    assert rows, (
        "no protected_data_refused audit event after a volunteered medical "
        f"detail (G3); audit types seen: {seen}"
    )
    payload = json.dumps(rows[0].payload, ensure_ascii=False).lower()
    for leaked in ("ansiedad", "medicaci", "anxiety", "medica"):
        assert leaked not in payload, (
            f"the refusal payload stores the disclosure it refuses (found '{leaked}')"
        )
    assert "not stored" in payload, (
        f"the refusal record does not state that nothing was stored: {payload}"
    )


def test_volunteered_medical_detail_in_portuguese_is_refused(sim_engine) -> None:
    driven = _drive(
        sim_engine,
        _persona("G3-REF-02", "Ines", "+34 600 881 002"),
        [VOLUNTEERED_MEDICAL_PT],
        world=False,
    )
    assert _refusal_rows(driven.audit), (
        "no refusal for the Portuguese medical wording; the term list must be multilingual"
    )


def test_normal_message_is_not_refused(sim_engine) -> None:
    driven = _drive(
        sim_engine,
        _persona("G3-REF-03", "Pablo", "+34 600 881 003"),
        [NORMAL_TEXT],
        world=False,
    )
    assert not _refusal_rows(driven.audit), (
        "a normal shift question must not be classified as protected volunteering"
    )


def test_check_is_non_vacuous_on_the_refusal(sim_engine) -> None:
    """The check must fail when the refusal row is removed, proving the
    detection is real and not an artefact of an empty fixture."""
    from evals.checks.deterministic import check_no_protected_data_stored

    driven = _drive(
        sim_engine,
        _persona("G3-REF-04", "Marta", "+34 600 881 004"),
        [VOLUNTEERED_MEDICAL],
        world=False,
    )
    assert check_no_protected_data_stored(driven.audit).passed, (
        "the check fails on a correctly refused conversation: "
        f"{check_no_protected_data_stored(driven.audit).evidence}"
    )
    without_refusal = replace(
        driven.audit,
        audit_events=[r for r in driven.audit.audit_events if r.event_type != REFUSAL_EVENT],
    )
    result = check_no_protected_data_stored(without_refusal)
    assert not result.passed, "the check passed without a refusal row: it is vacuous"
