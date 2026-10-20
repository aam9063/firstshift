# ADR-0002: The open shift, not the requisition, is the unit of work

- **Status:** accepted (phase 3, solution design).
- **Date:** 2027-02 (simulated project timeline).

## Context

The client's process today hires for positions. A candidate fills an "availability" dropdown once, the field dies in the ATS, and the rota never sees it: a candidate was rejected twice for "availability" without anyone asking what her hours actually were, and her real availability was exactly the hours restaurants suffer [T-candidate-b-08 to T-candidate-b-10, T-candidate-b-24]; a student answered "completa" because she did not understand the dropdown [T-candidate-a-20]; a churned hire's stated availability never reached the rota [T-churned-14]. Meanwhile the actual scarce object is concrete: a Friday and Saturday night shift at Benidorm Playa. ShiftGrid exposes open shifts and the rota locks Thursdays [T-hugo-12].

## Decision

The unit of work throughout recruiting, matching, scheduling and the first week is the open shift from ShiftGrid, not the requisition. A requisition is still created in HireDesk so Talent keeps control and reporting (the client's existing routine is preserved), but matching, screening questions, the offer, the first-shift scheduling and the day-before confirmation all reference a concrete open shift. Availability is collected as concrete shifts the candidate accepts, and that structure flows to the rota instead of dying in a form field.

## Consequences

- Screening questions become concrete and answerable: "which of these shifts can you take" instead of a dropdown [T-candidate-b-22].
- Accepting a concrete shift is a commitment, which supports the day-1 show lever (the commitment engine in O6 builds on it).
- The bench (O4) stores shift-fit people per restaurant against real shift patterns, so re-engagement is actionable, not a greeting.
- Failure mode: stale ShiftGrid data means the agent proposes shifts that do not exist. The design therefore reads open shifts live at matching time and re-validates the chosen shift before the offer.
- HireDesk remains the record of the requisition; a reconciliation between requisition state and shift state is needed so Talent reporting does not drift.
- Multi-tenant scoping applies at restaurant level from day one (C-O3), which the shift object carries naturally.

## Alternatives considered

- **Requisition-centric with a richer availability field.** Rejected: it is the observed failure mode; the field has already proven it does not reach the rota [T-churned-14].
- **Job-title matching with availability as free text.** Rejected: free text does not validate against the rota and recreates the same dead-end downstream.
- **Skip HireDesk requisitions entirely.** Rejected: Talent's control and reporting live there; breaking their routine would cost adoption for no speed gain.

## Evidence

- `design/constraints.md`: C-O3 (restaurant-level scoping from day one), C-T1 (ShiftGrid REST only).
- Discovery: [T-candidate-b-08 to T-candidate-b-10, T-candidate-b-24], [T-candidate-a-20], [T-churned-14] (the dead availability field), [T-candidate-b-22] (concrete asks get answered), [T-hugo-12] (Thursday lock).
- Design: `design/options.md` O2 (scored 4.10, second overall) and `design/decision-matrix.md` (evidence strength 5 for O2).
- Spec: `specs/03-solution-design.md` sections 3 and 6.
