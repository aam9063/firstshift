# ADR-0006: FirstShift owns the promise-to-payroll window as a per-hire status object that drives action

- **Status:** accepted (phase 3, solution design).
- **Date:** 2027-02 (simulated project timeline).

## Context

The hired-to-rota window is the largest funnel time sink (5.1 median days; offer to first shift 9 to 9.5 days), and discovery's systems review found that no system, team or report owns the transition between verbal yes and first schedulable shift. Nómina360 employee creation takes 3 to 6 days and gates scheduling [T-yolanda-20]; Sofía calls the waiting person "a promise" [T-sofia-18]; one observed hire took 11 days [T-yolanda-10]; the rota locks Thursdays [T-hugo-12]; the three chronic late documents are named in [T-sofia-10]. Everyone waits on everyone else and nobody sees the queue. The question for the design: who owns this window, and is ownership visibility or action?

## Decision

FirstShift owns the window with a per-person, per-hire status object (the promise-to-payroll tracker, O11). The object holds every blocking step with its state and age: which document is late, the day the Nómina360 creation was requested and where it sits in its 3-to-6-day range, whether the hygiene module is done, and when the rota unlocks relative to the Thursday lock. It is surfaced as a daily WhatsApp status line to the manager and People Ops. Critically, the tracker is built to drive one action per state (chase the missing document, nudge the Nómina360 queue, warn about the Thursday lock), not to display status; a state with no associated action is a design defect, not a feature. Two boundaries hold: FirstShift reads Nómina360 truth through the nightly CSV, never through optimistic API confirmations (C-T4, see ADR-0007), and it never writes contracts or registrations; the Nómina360 write path stays with People Ops as validated payloads (C-L9, [T-sofia-04, T-sofia-18]).

## Consequences

- The window stops being ownerless: every day of the 3-to-6-day Nómina360 wait has a named next action, which is the mechanism by which visibility becomes velocity.
- People Ops gets her stated win: knowing what is missing the same day it is missing [T-sofia-26], without a new system to log into (the status line is WhatsApp, per C-O1).
- The tracker depends on pre-boarding (O5) feeding it; without early document collection it degrades into a dashboard for a problem nobody can act on. The concept therefore ships O5 and O11 together.
- People-ops-sensitive data reaches managers' phones; the status line shows state and action ("alta requested day 2 of 6"), never salary or personal document contents.
- The Thursday-lock model becomes a shared fact the commitment engine and Pulse also read, so cutoffs are computed against the real rota calendar (C-T4, [T-hugo-12]).
- FirstShift takes on an ownership claim in the client's organization; the pilot charter must say explicitly that FirstShift drives, People Ops decides on the Nómina360 flow.

## Alternatives considered

- **A shared dashboard only (visibility without ownership).** Rejected: the option text names this failure directly; a tracker that shows the Nómina360 creation sitting at day 5 does not shorten it.
- **Assign ownership to an existing human role (People Ops coordinator).** Rejected: it adds a job to a team already stretched and recreates the single-point-of-forgetting the window has today; the agent drives, humans act.
- **Extend Nómina360 itself with a status tracker.** Rejected: it is a vendor system accessed only through documented REST (C-T1); there is no extension point, and IT's review gate makes custom integration infeasible in the pilot.
- **Optimistic API-based tracking.** Rejected: the July incident showed writes can be API-"confirmed" and absent [T-hugo-16, T-hugo-20]; building the tracker on optimistic reads would report ready states that are not true.

## Evidence

- `design/constraints.md`: C-L9 (People Ops owns the Nómina360 write path), C-T4 (CSV as the reliable read), C-O1 (WhatsApp surface), C-T1 (documented APIs only).
- Discovery: [T-sofia-04, T-sofia-10, T-sofia-18, T-sofia-20, T-sofia-26], [T-yolanda-10, T-yolanda-20], [T-hugo-12]; `discovery/systems-and-data.md` key finding that nothing owns the hired-to-rota transition.
- Design: `design/options.md` O11 (weighted total 3.72, fourth); `design/decision-matrix.md` (evidence strength 4); ADR-0007 for the CSV-truth boundary.
- Spec: `specs/03-solution-design.md` sections 3 and 6.
