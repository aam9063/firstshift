"""Controllable clock for the simulator (specs/04-prototype.md section 2).

The core never reads a clock: StateMachine.tick fires a timer when
``anchor + offset <= now`` with ``now`` injected by the caller. The
simulator owns that ``now``: a base time (the scenario load moment) plus a
persisted offset that advances by minutes/hours/days or jumps to the next
pending timer deadline. Because the offset lives on the scenario run row
(app/sim/store.py), advances survive between HTTP requests within a run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.policies import CONDITIONS, TIMER_DEFINITIONS
from app.core.state_machine import Application as CoreApplication
from app.core.state_machine import TimerDef


@dataclass(frozen=True)
class SimClock:
    """Wall-clock base plus a persisted offset; ``now`` is derived, never read."""

    base_at: datetime
    offset: timedelta = timedelta(0)

    @property
    def now(self) -> datetime:
        return self.base_at + self.offset

    def advanced(self, *, minutes: float = 0.0, hours: float = 0.0, days: float = 0.0) -> SimClock:
        """A clock moved forward by the requested amounts."""
        return SimClock(
            base_at=self.base_at,
            offset=self.offset + timedelta(days=days, hours=hours, minutes=minutes),
        )

    def at_next_timer(self, snapshot: CoreApplication) -> datetime | None:
        """The moment of the soonest timer that could still fire.

        Returns None when no timer is pending for the snapshot's state. A
        timer already due (deadline at or before the current now) yields the
        current now so the next tick fires it immediately. Conditions are
        evaluated at the deadline, matching how tick would judge them.
        """
        current = self.now
        candidates = [
            max(due_at, current)
            for _, due_at in pending_timer_deadlines(snapshot, current)
        ]
        if not candidates:
            return None
        return min(candidates)


def pending_timer_deadlines(
    snapshot: CoreApplication, now: datetime
) -> list[tuple[TimerDef, datetime]]:
    """Every declarative timer not yet fired whose deadline is still ahead.

    Mirrors the firing checks of StateMachine.tick (fired set, state match,
    anchor presence) but selects pending deadlines instead of due ones.
    """
    pending: list[tuple[TimerDef, datetime]] = []
    for timer in sorted(TIMER_DEFINITIONS, key=lambda d: d.offset):
        if timer.key in snapshot.fired_timers:
            continue
        if snapshot.state not in timer.states:
            continue
        anchor: datetime | None = getattr(snapshot, timer.anchor)
        if anchor is None:
            continue
        due_at = anchor + timer.offset
        if due_at <= now:
            continue
        if timer.condition is not None and not CONDITIONS[timer.condition](snapshot, due_at):
            continue
        pending.append((timer, due_at))
    return pending
