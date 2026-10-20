# ADR-0005: The bench is a consented, expiring, erasable pool inside the governed channel

- **Status:** accepted (phase 3, solution design).
- **Date:** 2027-02 (simulated project timeline).

## Context

The bench is the highest-scoring option in the matrix (O4, 4.18) because it formalizes what already works: Yolanda's roughly 25 "maybes" in her personal WhatsApp, hired by her directly before any requisition [T-yolanda-08, T-yolanda-14, T-yolanda-16]. But a persistent pool of re-contactable people is precisely where the DPO's red lines live. Consent must be explicit, per channel, with timestamp and notice version [T-laura-26] (C-L1, C-L2); retention must actually execute, not exist as a PDF [T-laura-08, T-laura-18] (C-L4); erasure must work end to end including the bench and conversation history (C-L5); and the pool must not push more candidate conversations into personal WhatsApp, which she names as a step backwards [T-laura-22] but accepts when the channel is governed and searchable [T-laura-24]. Get the consent design wrong and the flagship feature is the pilot's GDPR incident.

## Decision

A bench entry (`BenchEntry`) is created only with explicit re-engagement consent, captured at silver-medal time or at the moment a candidate is benched: the candidate sees a versioned notice and answers a one-tap consent question per channel. The entry stores the consent timestamp, the notice version and the consented channels; the agent re-engages only on consented channels and only while the entry is live. Retention executes: a bench entry has an expiry (configurable per the DPO's answer during the pilot, defaulting to 6 months), and an expired entry is anonymized automatically by a scheduled worker, not by a policy document. Erasure covers the bench: a data subject request deletes or exports the entry, its consent record and its conversation history, ending in the `erased` state. Managers see the bench as their restaurant's list, surfaced in WhatsApp and in the HQ console, with every re-engagement logged: the bench absorbs the personal-WhatsApp habit into the governed channel rather than competing with it.

## Consequences

- Every re-engagement send is provably consented per channel with version and timestamp, which is exactly the proof the DPO asks for [T-laura-26].
- The expiry worker makes retention real: the test "a record older than the configured retention is gone from every store without manual intervention" (C-L4) runs against the bench like against any candidate record.
- Consent decay is visible: a bench contact that never responds consumes its expiry naturally instead of lingering forever, fixing the forever-by-default pattern [T-laura-08].
- The bench is only as good as its consent UX: a candidate who does not understand the consent question never becomes re-contactable, so silver-medal yield depends on the message catalog quality.
- An expiry default (6 months) is a design assumption until Laura states her number, an explicit open question from discovery; it is configurable rather than hard-coded for exactly that reason.
- Managers keep visibility of "their" people, respecting the adoption constraint [T-yolanda-26], while the data finally lives where the DPO can find it [T-laura-12].

## Alternatives considered

- **Bench with implicit consent carried over from the original application.** Rejected: applying weeks later on the strength of an application-time consent is not the explicit, per-channel, versioned consent the DPO requires (C-L1, C-L2).
- **No bench; re-source every gap from scratch.** Rejected: it discards the strongest TTFPS lever and the observed working method [T-yolanda-08].
- **Bench inside managers' personal WhatsApp with an HQ export.** Rejected: it deepens the shadow channel the DPO cannot search [T-laura-12] and fails C-L4 and C-L5 by construction.
- **Bench with unlimited retention "while consented".** Rejected: consent without an expiry recreates forever-by-default with extra steps; time-bounded re-consent is the defensible schedule.

## Evidence

- `design/constraints.md`: C-L1, C-L2 (consent with version and channel), C-L4 (retention that executes), C-L5 (end-to-end erasure), C-O1 (no new manager portal; the bench surfaces in WhatsApp).
- Discovery: [T-laura-08, T-laura-12, T-laura-18, T-laura-22, T-laura-24, T-laura-26], [T-yolanda-08, T-yolanda-14, T-yolanda-16, T-yolanda-26].
- Design: `design/options.md` O4 (top-scored option, 4.18; its "what would have to be true" names consent, retention and erasure verbatim); `design/guardrails.md` G2, INV-5.
- Spec: `specs/03-solution-design.md` sections 3 and 6.
