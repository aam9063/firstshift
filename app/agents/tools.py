"""Tool registry and the per-state allow-list dispatcher (G6).

The allow-list table below is the design seed from design/agents.md ("Per-
state tool allow-list seeds"). The dispatcher is the enforcement point: every
tool call, whatever its origin, is checked against the current state's row
before execution. A call outside the row fails closed and is recorded as a
``tool.call`` event with status ``rejected`` by the caller (prompt injection
cannot trigger tools outside the allow-list, G6).

Rows may be narrowed without ceremony; widening one requires a recorded
reason. The ``benched`` row is deliberately empty: re-engagement (design row
31) is a system transition with its own consent guard, not an agent tool.
Terminal states have no rows at all: no agent acts in them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSpec:
    """What the model sees for one tool."""

    name: str
    description: str


@dataclass(frozen=True)
class ToolRejection:
    tool_name: str
    agent: str
    state: str
    reason: str


# state value -> agent -> allowed tool names (design/agents.md seed table)
_ALLOW_LIST: dict[str, dict[str, frozenset[str]]] = {
    "new": {"recruit": frozenset({"capture_consent"})},  # first-message reply path only
    "contacted": {"recruit": frozenset({"capture_consent"})},
    "consented": {"recruit": frozenset({"save_screening_answers", "save_language_tag"})},
    "screening": {
        "recruit": frozenset(
            {
                "save_screening_answers",
                "save_language_tag",
                "get_open_shifts",
                "propose_shifts",
                "add_to_bench",
            }
        )
    },
    "matched": {
        "recruit": frozenset({"propose_shifts", "book_interview_slot", "add_to_bench"}),
        "onboard": frozenset({"request_documents", "enroll_training"}),
    },
    "interview_booked": {"recruit": frozenset({"book_interview_slot"})},  # first re-book only
    "interviewed": {"recruit": frozenset({"request_manager_decision"})},
    "pending_manager_decision": {
        "recruit": frozenset({"request_manager_decision"}),  # idempotent re-send
        "onboard": frozenset({"request_documents", "enroll_training", "check_training_status"}),
    },
    "offer_sent": {
        "onboard": frozenset(
            {
                "request_documents",
                "check_document_status",
                "enroll_training",
                "check_training_status",
                "get_tracker_status",
            }
        )
    },
    "offer_accepted": {
        "onboard": frozenset(
            {
                "request_documents",
                "check_document_status",
                "enroll_training",
                "check_training_status",
                "get_tracker_status",
            }
        )
    },
    "preboarding": {
        "onboard": frozenset(
            {
                "request_documents",
                "check_document_status",
                "enroll_training",
                "check_training_status",
                "get_tracker_status",
            }
        )
    },
    "ready_for_rota": {"onboard": frozenset({"schedule_first_shift", "get_tracker_status"})},
    "first_shift_scheduled": {
        "onboard": frozenset(
            {"send_first_shift_brief", "activate_backup", "schedule_first_shift"}
        )
    },
    "first_shift_confirmed": {"onboard": frozenset({"send_first_shift_brief"})},
    "first_shift_worked": {
        "pulse": frozenset({"get_employee_rota", "report_issue_to_manager", "request_swap"}),
        "onboard": frozenset({"send_first_shift_brief"}),  # day-0 check-in
    },
    "active_week1": {
        "pulse": frozenset(
            {"get_employee_rota", "report_issue_to_manager", "request_swap",
             "record_manager_rating"}
        )
    },
    "active_day30": {"pulse": frozenset({"record_retention_signal", "record_manager_rating"})},
    # "benched": narrowed to empty on purpose (re-engagement is a core
    # transition, not an agent tool). Terminal states are absent entirely.
}

TOOL_DESCRIPTIONS: dict[str, str] = {
    "capture_consent": "Record the candidate's consent for this channel, with notice version.",
    "save_language_tag": "Store the candidate's explicitly stated language preference.",
    "save_screening_answers": (
        "Store eligibility facts: right to work, minimum-age check, distance and transport."
    ),
    "get_open_shifts": "List the open shifts at the application's restaurant.",
    "propose_shifts": "Propose concrete open shifts; a recommendation, never a promise.",
    "book_interview_slot": "Book one of the manager's open interview slots.",
    "add_to_bench": "Add the candidate to the consented per-restaurant bench.",
    "request_manager_decision": "Send the manager the summary and request the hiring decision.",
    "request_documents": "Send the candidate the mock document upload link.",
    "check_document_status": "Read whether Nómina360 documents are complete.",
    "enroll_training": "Enroll the candidate in a LearnBite module.",
    "check_training_status": "Read LearnBite module completion.",
    "schedule_first_shift": "Propose a first-shift slot; the manager decides (row 23).",
    "send_first_shift_brief": (
        "Send the concrete first-shift brief: address, entrance, uniform, who to ask for."
    ),
    "activate_backup": "Activate the named bench backup at the confirmation cutoff (T4).",
    "get_tracker_status": "Read the O11 hired-to-rota tracker facts.",
    "get_employee_rota": "Read the employee's rota to detect conflicts.",
    "report_issue_to_manager": "Route a surfaced issue to the manager with a suggested action.",
    "request_swap": "Route a shift swap request to the manager, who decides (C-O1).",
    "record_manager_rating": "Record the week-2 manager rating (1 to 5).",
    "record_retention_signal": "Record the day-30 retention outcome and its operational cause.",
}


class ToolDispatcher:
    """Pure allow-list checks; no I/O, no state of its own."""

    def allow_list(self) -> dict[str, dict[str, frozenset[str]]]:
        """The full table as plain data (for tests and the console meta API)."""
        return _ALLOW_LIST

    def tools_for(self, agent: str, state: str) -> tuple[ToolSpec, ...]:
        """The tools the agent may use in this state, as model-facing specs."""
        names = _ALLOW_LIST.get(state, {}).get(agent, frozenset())
        return tuple(
            ToolSpec(name=name, description=TOOL_DESCRIPTIONS.get(name, ""))
            for name in sorted(names)
        )

    def validate(self, tool_name: str, agent: str, state: str) -> ToolRejection | None:
        """A rejection reason when the call is not allowed, else None.

        Unknown tools are rejected; known tools must appear in the current
        state's row for the requesting agent. This check is the single G6
        enforcement point and is applied regardless of who asks.
        """
        if tool_name not in TOOL_DESCRIPTIONS:
            return ToolRejection(
                tool_name=tool_name,
                agent=agent,
                state=state,
                reason=f"unknown tool '{tool_name}'",
            )
        allowed = _ALLOW_LIST.get(state, {}).get(agent, frozenset())
        if tool_name not in allowed:
            return ToolRejection(
                tool_name=tool_name,
                agent=agent,
                state=state,
                reason=(
                    f"tool '{tool_name}' is not in the {state} allow-list for agent "
                    f"'{agent}' (G6); allowed: {sorted(allowed) or 'none'}"
                ),
            )
        return None


def tools_for(agent: str, state: str) -> tuple[ToolSpec, ...]:
    """Module-level convenience over a shared pure dispatcher."""
    return ToolDispatcher().tools_for(agent, state)
