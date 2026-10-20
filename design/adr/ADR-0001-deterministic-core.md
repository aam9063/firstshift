# ADR-0001: Deterministic core with the LLM at the edge

- **Status:** accepted (phase 3, solution design).
- **Date:** 2027-02 (simulated project timeline).

## Context

FirstShift talks to candidates and managers in natural language on WhatsApp, but it also runs a hiring process with legal weight: consent records, offers, rejections, scheduling and writes into Nómina360. Two failure modes are unacceptable. First, the DPO's line is explicit: "no automated decisions about people. Assist, yes. Decide, no. Show me the logs and I can sleep" [T-laura-18, T-laura-20], and Jordi vetoes black-box rejection outright: the final rejection is always signed by a person [T-jordi-22]. An LLM deciding state transitions would be exactly the automated decision-making that GDPR article 22 and the EU AI Act high-risk framing (C-L6, C-L7) prohibit. Second, the operational writes are unforgiving: Nómina360's rate limit "is not a suggestion" [T-hugo-14], writes must be idempotent under an IT-controlled key (C-T5) and traceable end to end (C-T6). A probabilistic component deciding when to write is unauditable in both senses.

At the same time, the conversation itself cannot be a rigid script: candidates answer in free text, in three languages, and concrete shift questions get answered where dropdowns do not [T-candidate-b-22]. The LLM is genuinely needed at the edge.

## Decision

The hiring process is a deterministic state machine in plain Python (the core). The LLM has exactly three jobs: (a) hold the natural-language conversation, (b) extract structured data from free text into Pydantic models, and (c) summarize for humans. It never decides a state transition, never decides eligibility, and never decides scheduling. Every LLM output that feeds the core is validated against a schema; invalid output triggers a re-ask, never a guess. Agents call tools; tools call the deterministic core; the core decides. An agent never calls a client system directly.

The guardrails that depend on this decision are specified in `design/guardrails.md` (G3, G4, G6 and invariants INV-1, INV-2).

## Consequences

- Every transition is testable as a pure function: property tests cover the invariants (no `offer_sent` without manager approval, no `not_selected` without a human actor) with no mocking of an LLM.
- The audit trail is exact: who, what, when and on what grounds, because transitions are code, not prompts [T-laura-18].
- LLM failures degrade gracefully: a failed extraction becomes a re-ask to the candidate, not a corrupted record.
- Cost and latency are bounded per turn instead of per decision; the expensive path is conversation, not state.
- The agent's behavior is evaluable separately from the process (golden conversations and adversarial evals in `evals/`).
- Anything the LLM cannot be trusted to do (matching, cutoffs, backup activation) must be expressed as explicit policy in the core, which is more design work up front.

## Alternatives considered

- **LLM-driven agentic loop (the model decides next actions and transitions).** Rejected: it is the direct violation of the DPO's line and of C-L6/C-L7, it cannot be property-tested, and an injected or hallucinated transition could trigger a client write.
- **Fully scripted IVR-style flow with no LLM.** Rejected: candidates demonstrably answer free text and concrete questions on WhatsApp [T-candidate-b-22], and forcing menus recreates the front-door failure (41.0% never contacted) in a new form.
- **LLM proposes, second LLM verifies.** Rejected for the decision path: verification by a second probabilistic component is still probabilistic; only the deterministic core with human decisions satisfies the evidence.

## Evidence

- `design/constraints.md`: C-L6 (named human decision-maker, article 22), C-L7 (EU AI Act high-risk oversight), C-T5, C-T6 (idempotent, traceable writes).
- Discovery: [T-laura-18, T-laura-20] (no automated decisions, auditability), [T-jordi-22] (human-signed rejections), [T-hugo-14, T-hugo-22] (write-path discipline), [T-candidate-b-22] (free-text channel works).
- Spec: `specs/03-solution-design.md` section 6 ("Write ADRs for at least: deterministic core vs LLM-driven flow").
