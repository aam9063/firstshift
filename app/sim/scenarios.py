"""Scenario definitions D1-D7 (F07, T2) per specs/04-prototype.md section 3.

Each scenario is a JSON file in app/sim/scenarios/ describing:
- the HireDesk application payload the load webhook fires,
- the manager who will act on it,
- scripted steps: candidate/manager/system messages (system stands in for
  the agent loop until T1 lands), each optionally carrying the core event it
  triggers plus guard facts (snapshot updates), and clock steps
  (advance by minutes/hours/days or jump to the next timer deadline).

Relative datetimes in payloads/snapshots ({days, hours, minutes} objects)
are resolved against the run's base_at by resolve_relative_datetimes, so a
scenario reads as deltas from the application moment, like the demo.

Loading a scenario (POST /api/sim/scenarios/{id}/load) resets the simulator
stores and fires the webhook; the scripted steps are then executed by the
console (or tests) one call at a time through POST /api/sim/messages and
POST /api/sim/clock/advance, exactly the three simulator API rows of
specs/04b-console.md section 2.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, ValidationError

SCENARIOS_DIR = Path(__file__).parent / "scenarios"


class ManagerSpec(BaseModel):
    """The named human who acts on the application in the simulator."""

    id: str
    name: str


class ClockStep(BaseModel):
    """A clock control: fast-forward by amounts or jump to the next timer."""

    kind: Literal["clock"]
    minutes: float = 0.0
    hours: float = 0.0
    days: float = 0.0
    next_timer: bool = False


class MessageStep(BaseModel):
    """One scripted message on a simulated phone, optionally a core event.

    system stands in for the agent loop until T1. expect_reject marks steps
    whose dispatch the core must reject (D6's injection posture): the driver
    expects a 409 and no transition.
    """

    kind: Literal["message"]
    role: Literal["candidate", "manager", "system"]
    text: str
    event: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    snapshot: dict[str, Any] = Field(default_factory=dict)
    expect_reject: bool = False


# Discriminated step union used by Scenario.steps below.
Step = Annotated[ClockStep | MessageStep, Field(discriminator="kind")]


class Scenario(BaseModel):
    """One demo scenario: application payload, manager, scripted steps."""

    id: str
    name: str
    proves: str
    description: str
    application: dict[str, Any]
    manager: ManagerSpec
    steps: list[Annotated[ClockStep | MessageStep, Field(discriminator="kind")]]
    notes: list[str] = Field(default_factory=list)


def _load_all() -> dict[str, Scenario]:
    scenarios: dict[str, Scenario] = {}
    for path in sorted(SCENARIOS_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        try:
            scenario = Scenario.model_validate(raw)
        except ValidationError as exc:  # pragma: no cover - definition bug
            raise RuntimeError(f"invalid scenario file {path.name}: {exc}") from exc
        scenarios[scenario.id] = scenario
    return scenarios


_CACHE: dict[str, Scenario] | None = None


def scenario_ids() -> list[str]:
    return sorted(_scenarios())


def _scenarios() -> dict[str, Scenario]:
    global _CACHE
    if _CACHE is None:
        _CACHE = _load_all()
    return _CACHE


def get_scenario(scenario_id: str) -> Scenario:
    """The scenario definition, or KeyError for an unknown id."""
    scenarios = _scenarios()
    if scenario_id not in scenarios:
        raise KeyError(scenario_id)
    return scenarios[scenario_id]


def resolve_relative_datetimes(value: Any, base: datetime) -> Any:
    """Resolve {days, hours, minutes} objects into base + timedelta.

    Relative deltas keep scenario files readable as offsets from the
    application moment. ISO strings and everything else pass through.
    """
    if isinstance(value, dict):
        keys = set(value)
        if keys and keys <= {"days", "hours", "minutes"} and all(
            isinstance(v, (int, float)) for v in value.values()
        ):
            return base + timedelta(
                days=float(value.get("days", 0.0)),
                hours=float(value.get("hours", 0.0)),
                minutes=float(value.get("minutes", 0.0)),
            )
        return {key: resolve_relative_datetimes(item, base) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_relative_datetimes(item, base) for item in value]
    return value
