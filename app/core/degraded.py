"""Degraded-mode gating (F12 T2, S4): the pure flow -> client system mapping.

specs/06-integration-rollout.md section 2: "a degraded adapter pauses only the
flows that need it, and candidates get a holding message instead of silence".

This module is pure: no I/O, no imports from the API or adapter layers. The
health registry (app/api/health.py) produces the adapter status map; the
dispatch path (app/services/scripted.py) consults the mapping before it
dispatches an event and pauses the flow when a required system is degraded.

Status semantics (deterministic, tested):

- ``ok``: the adapter's health probe succeeded. The flow runs.
- ``degraded``: the probe failed or timed out. Only the flows that name this
  system pause; every other flow keeps working.
- ``unknown``: the adapter is missing, not constructible or has no probe.
  This is a visibility gap, not an observed outage: it never pauses a flow,
  because silently silencing candidates is the one failure the spec forbids.
  The health endpoint surfaces unknown so a human can decide.
"""

from __future__ import annotations

from collections.abc import Mapping

# Health statuses produced by app/api/health.py.
STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"
STATUS_UNKNOWN = "unknown"

# The client systems a flow cannot proceed without. One entry per flow named
# by the feature task; a flow absent from EVENT_FLOWS below is never gated.
FLOW_REQUIRED_SYSTEMS: dict[str, frozenset[str]] = {
    "first_contact": frozenset({"whatsapp"}),
    "reminder": frozenset({"whatsapp"}),
    "tracker_completion": frozenset({"nomina360"}),
    "shift_matching": frozenset({"shiftgrid"}),
    "training_enrollment": frozenset({"learnbite"}),
}

# Core event -> flow. Only events whose effects need a client system are
# mapped: first contact (the outbound first message), every reminder lane,
# the tracker completion gate (Nómina360 CSV truth) and the two ShiftGrid
# touchpoints of shift matching (the fit read and the first-shift write).
# Training enrollment has no core event yet (the hygiene module arrives as a
# snapshot flag); the flow exists here so the mapping is complete and the
# event can be attached when the core grows it.
EVENT_FLOWS: dict[str, str] = {
    "intake_processed": "first_contact",
    "no_reply_nudge_1": "reminder",
    "no_reply_nudge_2": "reminder",
    "interview_reminder_24h": "reminder",
    "interview_reminder_2h": "reminder",
    "manager_decision_remind": "reminder",
    "manager_decision_escalate": "reminder",
    "shift_fit_matched": "shift_matching",
    "first_shift_picked": "shift_matching",
    "tracker_completed": "tracker_completion",
}

# The versioned catalog template the candidate receives instead of silence.
HOLDING_TEMPLATE = "holding"


def flow_paused(flow: str, adapter_statuses: Mapping[str, str]) -> str | None:
    """The blocking system for one flow, or None when the flow may run.

    Returns the required system's name when the flow needs it and that
    system is degraded; None otherwise (ok, unknown and absent statuses all
    let the flow run).
    """
    required = FLOW_REQUIRED_SYSTEMS.get(flow)
    if not required:
        return None
    for system in sorted(required):
        if adapter_statuses.get(system) == STATUS_DEGRADED:
            return system
    return None


def pause_for_event(
    event: str, adapter_statuses: Mapping[str, str]
) -> tuple[str, str] | None:
    """(flow, blocking system) when this event's flow is paused, else None.

    Events outside every flow return None: gating only ever applies to the
    flows that actually need a client system.
    """
    flow = EVENT_FLOWS.get(event)
    if flow is None:
        return None
    system = flow_paused(flow, adapter_statuses)
    if system is None:
        return None
    return (flow, system)

# Process-wide last-known statuses. The health endpoint publishes here (and
# tests set them directly); an empty map means "nothing known", and unknown
# never pauses a flow (S4: a degraded adapter pauses only what needs it).
_KNOWN_STATUSES: dict[str, str] = {}


def known_statuses() -> Mapping[str, str]:
    """The last-known adapter statuses used by non-scripted dispatch paths."""
    return dict(_KNOWN_STATUSES)


def set_known_statuses(statuses: Mapping[str, str] | None) -> None:
    """Replace the known statuses (tests and the health publish path)."""
    _KNOWN_STATUSES.clear()
    if statuses:
        _KNOWN_STATUSES.update(statuses)

