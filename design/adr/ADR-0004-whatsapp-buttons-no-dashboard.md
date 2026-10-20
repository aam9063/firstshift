# ADR-0004: Manager decisions arrive as WhatsApp buttons, never as a dashboard

- **Status:** accepted (phase 3, solution design).
- **Date:** 2027-02 (simulated project timeline).

## Context

Managers run hiring from their personal WhatsApp: Yolanda keeps her "maybes" bench there and hired her last worker from it before any requisition existed [T-yolanda-14, T-yolanda-16, T-yolanda-08]. Raúl is categorical about portals [T-raul-26]. The CPO is equally clear that adoption decides the pilot: "Si Yolanda no lo usa en Benidorm, esto está muerto" [T-marta-22]. The natural instinct when building an agent product is a manager dashboard for approvals. That instinct is contradicted by the evidence, and the architecture rules forbid it: the console is for HQ oversight, never a step for managers. Decisions also need a record: today's approvals are side conversations that are never logged, which is both a measurement gap (no baseline approval latency) and a compliance gap the DPO calls her biggest headache in hiring [T-laura-12, T-laura-24].

## Decision

Every decision a manager owns (interview slot, offer approval, first-shift slot, backup activation, swap resolution) arrives as one WhatsApp message: a short summary of the facts and at most two or three quick-reply buttons plus free text, answerable in one tap. There is no manager login, portal or password anywhere in the system. Every button reply is logged with who, what and when, which turns today's unrecorded side chats into an audit trail. The web console exists for HQ (Talent, DPO, Ops) only and reads through the FirstShift API; managers never touch it.

## Consequences

- Behavior change is minimized to what the evidence supports: the pattern is the channel managers already use [T-yolanda-26], the only change is that it is logged.
- The decision log satisfies the DPO and is, in her words, a compliance improvement over personal WhatsApp [T-laura-18, T-laura-24].
- Latency is measurable from day one: button replies are timestamped events, fixing the H5 attribution gap.
- Message design is constrained and must be disciplined: every decision message stands alone, no navigation, no multi-screen flows (C-O2). Complex context is summarized, not linked.
- Deep or contentious decisions (a borderline rejection) may need more than buttons; the free-text escape and the escalation path to the area HRBP cover this, at the cost of some decisions becoming plain replies instead of clean one-tap events.
- Provider constraints (WhatsApp interactive-message limits) cap button count and length; the message catalog is the single place that manages this.

## Alternatives considered

- **Manager web dashboard with notifications.** Rejected: Raúl rejects portals [T-raul-26], and a login step reintroduces exactly the friction that keeps approvals in side chats today.
- **Email approvals.** Rejected: slower, not one-tap, and managers on shift do not live in email.
- **Buttons in WhatsApp plus a read-only mirror dashboard for managers.** Rejected as scope creep: it duplicates the console for an audience that asked for nothing, and the architecture rule keeps the console HQ-only.

## Evidence

- `design/constraints.md`: C-O1 (no new app or dashboard for managers; every manager action is a WhatsApp quick reply), C-O2 (at most two or three buttons plus free text), C-L6 (named decision-maker on record).
- Discovery: [T-raul-26], [T-yolanda-08, T-yolanda-14, T-yolanda-16, T-yolanda-26], [T-marta-22], [T-candidate-b-22], [T-laura-12, T-laura-18, T-laura-24].
- Design: `design/options.md` O7 (the manager surface of the winning combination); `design/decision-matrix.md` (O7 scored 3.62; demo-ability 5).
- Spec: `specs/03-solution-design.md` sections 3 and 6; `specs/04b-console.md` (console audience is HQ only).
