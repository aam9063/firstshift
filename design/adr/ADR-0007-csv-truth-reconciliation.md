# ADR-0007: The nightly Nómina360 CSV is the confirmation gate for "ready for the rota"

- **Status:** accepted (phase 3, solution design).
- **Date:** 2027-02 (simulated project timeline).

## Context

Nómina360's write API has a documented quirk with operational teeth: validation failures return HTTP 200 with an error body, which is how the July incident produced silent failures [T-hugo-16, T-hugo-20]. Hugo's own rule is that the nightly CSV export is the reliable read: "what is in the file is what is actually in the system" [T-hugo-18], and C-T4 makes it testable: a write is not counted as confirmed until the next CSV shows it. The failure mode this prevents is not cosmetic: a hire told "you start Saturday" whose alta silently failed will not show up, or worse, works unregistered, which Sofía names as a hard line ("no unregistered people working shifts" [T-sofia-20]). This is what "no-show" looks like when the cause is operational, not motivational, and it lands directly on the day-1 show metric.

## Decision

FirstShift treats the nightly CSV export as the confirmation gate: a nightly reconciliation job parses the export and downgrades any employee-creation write that the API reported as confirmed but that is absent from the file. "Ready for the rota" (the state that unlocks first-shift scheduling) is signaled only on CSV-confirmed truth. A mismatch raises an alert to IT and People Ops with the idempotency key and the compensating action from the runbook attached (C-T6, C-T7). The one-day confirmation lag is modeled explicitly into the commitment engine's cutoffs and the promise-to-payroll tracker's timeline, rather than hidden.

## Consequences

- The day-1 failure mode with an operational cause becomes detectable before day 1, not after.
- "Ready" is always true when shown, at the cost of up to a day of confirmation lag; scheduling near the Thursday lock must account for it, which the cutoff math does explicitly.
- Hugo's domain is entered on his terms: the reconciliation job lives inside his design review gate, which is treated as a hard gate, not a formality [T-hugo-22].
- The job depends on the CSV export being stable and parseable; a malformed export is a first-class alert (it cannot silently pass as "no mismatches"), since C-T3's lesson generalizes: never infer success from an absence of errors.
- Reconciliation turns C-T3 and C-T4 from policies into executable tests: the injected error-body-200 fixture and the API-confirmed-but-absent-CSV case are both automated test cases.
- Writes that fail reconciliation enter the compensating-action flow (correction record, cancellation, or a manual procedure owned by People Ops), which must exist per write type before go-live (C-T7).

## Alternatives considered

- **Trust the HTTP 200 response.** Rejected outright: it is the July incident [T-hugo-16, T-hugo-20], and C-T3 exists precisely because status codes lie here.
- **Verify by re-reading the record through the API.** Rejected: reads are subject to the same undocumented throttling behavior (C-T2), the read-after-write semantics are not documented, and Hugo has already named the CSV as the reliable read [T-hugo-18].
- **Real-time reconciliation against an hourly export.** Rejected: no evidence an hourly export exists or is supported; building one is an undocumented integration (C-T1) inside a 5-day pilot. The nightly cadence is what is documented and trusted.
- **Alert-only reconciliation that leaves "ready" on optimistic confirmation.** Rejected: it detects the failure but still lets the state machine tell a hire "you start Saturday" on false grounds; the gate must gate.

## Evidence

- `design/constraints.md`: C-T3 (validate by body, never status alone), C-T4 (CSV verification, downgrade test), C-T6, C-T7 (queryability and compensating actions), C-T2 (throttling treated as undocumented).
- Discovery: [T-hugo-14, T-hugo-16, T-hugo-18, T-hugo-20, T-hugo-22], [T-sofia-20].
- Design: `design/options.md` O12 (weighted total 3.64, fifth; compliance-risk inverse score 5, the lowest-risk option scored); `design/guardrails.md` INV-9; ADR-0006 (the tracker consumes CSV-confirmed state).
- Spec: `specs/03-solution-design.md` sections 6 and 7 (the nightly reconciliation job and the Nómina360 quirk are named components of the architecture).
