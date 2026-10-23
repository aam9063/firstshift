# FirstShift simulated pilot: day-90 steering committee readout (Lumbre Burger Group)

**Evidence base:** `docs/pilot-sim-day90.json`, the completed 90-day simulated run (seed 42, label day90, window 2025-06-02 to 2025-08-30, 2,279 pilot applications across the 12 pilot restaurants through the real pipeline, 558 control applications across the 3 control restaurants through the as-is statistical model). Deterministic checks passed on all 2,279 pilot conversations (0 failures), so the run is valid by the pilot's own contract.

**Run provenance, disclosed in full:**

1. The run authorized for this document (`uv run python -m evals.pilot --days 90 --seed 42 --label day90`, 900 second budget) was started once by this worker and did not finish inside the budget: it reached conversation P619 and was terminated. A killed run writes no artifacts.
2. A completed day-90 artifact was then found at `docs/pilot-sim-day90.json`, written by a concurrent run on the shared worktree (its meta records a start time of 2026-10-23T17:41:42Z). This worker did not observe that run.
3. The counts are nonetheless safe to use, for three reasons: the pipeline is deterministic for a given seed and day count (`evals/pilot.py`, pinned by `tests/test_pilot_sim.py`), each run executes in an isolated throwaway database schema that is dropped on exit, and this worker verified the artifact's internal consistency (weekly arrival sums, final-state arithmetic, show-rate and cost recomputation; all exact).
4. If the steering committee requires first-hand provenance, rerunning the same command (about one hour, no timeout) reproduces the same counts.

**What this readout cannot fill:** 30-day retention, manager hiring hours per week, coverage of peak hours, candidate CSAT and escalation acknowledgment latency are not produced by the simulation at any day count. They are real-pilot measurements, and the day-90 gate depends on them; see section 5.

> Simulation caveat: this is a simulation with synthetic behavior, useful to find failure modes and to size impact, not proof of real-world effect. Every number below is a simulated outcome.

---

## 1. Results vs the pilot charter

> Simulation caveat: this is a simulation with synthetic behavior, useful to find failure modes and to size impact, not proof of real-world effect. The evidence column comes from the day-90 simulated run (docs/pilot-sim-day90.json).

| Charter day-90 target | Simulated evidence (90-day window) | Status against the target |
| --- | --- | --- |
| TTFPS 14 days or less | 6.33 days median, application to first worked shift, vs 27.67 days in the control model and 27.3 in discovery | Met in simulation, with the structural caveat that the simulated world attends every interview and the persona reliability is not calibrated to the client pool |
| Contacted rate 95% or more | 100% (2,279 of 2,279 applicants contacted, median 0 minutes) vs 59% baseline | Met, but structurally: first contact is synchronous in the pipeline, so the simulation cannot fail this target |
| Interview show rate 80% or more | 100% in the pilot arm (the simulated world confirms attendance); control model 62.1% vs 62% baseline | Not evidenced: the 38% interview no-show problem only exists in the control model, so the pilot arm's 100% proves nothing |
| Day-1 no-show under 8% | 24.5% (502 of 2,051 hires scheduled and prepared, first shift never worked) | Not met. This is the one red number of the run, and it is stable across windows (23.9% at day 30) |
| 30-day retention 80% or more | Not computed by the simulation | Not measurable: the simulation ends at the first worked shift |
| Manager hiring time 2 hours per week or less | Not computed by the simulation | Not measurable |
| Coverage on trend (4% or less of peak hours understaffed) | Not computed by the simulation | Not measurable |
| Guardrails: CSAT median 4.0+, fairness parity, escalation ack 30 min, zero GDPR incidents, DPIA signed | Fairness: no group flagged across language, nationality group and age band (four-fifths ratios 0.97 to 1.00, all groups). Deterministic checks: 0 failures in 2,279 conversations. CSAT and acknowledgment latency: not computed. DPIA signature: a real-world precondition, not simulated | Partially green: fairness and deterministic checks green in simulation; the rest unmeasured |

Hypothesis status at day 90 (definitions and kill thresholds in `design/hypotheses.md`):

- **H1 (fast first contact converts the silent queue):** supported in simulation on its contact metrics (100% contacted, 0-minute median, against 59% and 3.9 days in discovery). Its show-rate claim is not evidenced, for the structural reason above.
- **H2 (concrete shift availability lifts retention):** not testable in this run; retention is not computed. Open for the real pilot.
- **H3 (pre-collection cuts offer-to-first-shift time):** supported in simulation: the 6.33-day TTFPS proxy is far inside H3's 6-day kill threshold territory for offer-to-first-shift.
- **H4 (day-before confirmation plus named backup cuts day-1 no-shows):** failed its own bar in simulation: 24.5% is above the 12% kill threshold ("drop the backup mechanism as ineffective and test the confirmation alone"). The honest reading: in the simulated world the confirm-plus-backup machinery did not hold the line, so the real pilot should test the confirmation in isolation and treat the persona reliability caveat (the pool's hidden reliability was drawn for evaluation coverage, not calibrated to the client's applicant pool) as unquantified upside.

## 2. Cost per hire vs baseline

> Simulation caveat: this is a simulation with synthetic behavior, useful to find failure modes and to size impact, not proof of real-world effect. The token counts come from the scripted offline model, not a live LLM, and human supervision time is not in the agent number.

The formula, from the pilot's cost accounting (`evals/metrics.py`, `evals/pricing.py`):

```
agent cost per hire (USD) = total agent cost in the window / hires
                          = 5.985664 USD / 2,051 hires
                          = 0.002918 USD per hire
```

- Total agent cost: token counts of every `agent.turn` in the 90-day window priced at the scripted model's rates (`total_cost_usd` 5.985664 in docs/pilot-sim-day90.json).
- Hires: 2,051 applications that reached the hired state in the window (of 2,279 applications).
- Baseline: 420 EUR per hire, all-in human cost of the as-is process (brief section 4; the control arm carries the same 420 EUR per hire, 42 control hires from 558 arrivals).

The honest comparison is not 0.002918 USD against 420 EUR: the agent number excludes the LLM cost at a real model (the scripted model's token counts understate a live gpt-4.1-mini run), the human supervision the design requires (Talent supervising conversations, managers deciding), and the fixed platform cost. What the number does establish is that model tokens are a negligible line item even with a thousandfold underestimate. The real cost question the simulation leaves open is human time, which is exactly the charter's manager-hours target and remains unmeasured (section 5).

## 3. What we learned

> Simulation caveat: this is a simulation with synthetic behavior, useful to find failure modes and to size impact, not proof of real-world effect. Each item names the count the simulation actually produced; counts scale linearly from the day-30 window (docs/pilot-sim-day30.md), as expected from a deterministic pipeline.

- **Silence is the normal case, not the exception.** 228 candidates went quiet mid-process and were benched by the timers (48 h bench timer, no-reply policy). A hiring system must be built around non-response, not around the compliant candidate.
- **Day-1 reliability is the residual gap, and it does not improve with volume.** 502 hires (24.5%) were scheduled, prepared and still did not show up on day 1, essentially the same rate as the day-30 window (23.9%). The front door works; the last mile before the first shift is where the process loses people, and more volume does not fix it.
- **The human decision queue scales linearly too.** 228 manager decision SLA breaches in 90 days (about 17 per week); every one needed a human, and the 8-hour HRBP escalation fired each time.
- **Candidates volunteer protected data unprompted, constantly.** 1,368 refusals: the agent declined to store volunteered protected information every time (guardrail G3). The DPO-approved wording for those moments is high-frequency copy, not an edge case.
- **The guardrails held at full volume.** 0 deterministic check failures in 2,279 conversations, and no fairness group flagged (minimum four-fifths ratio 0.973, all 11 group rows clean).
- **The control arm stabilized at volume.** Over 90 days the as-is model reproduces every discovery baseline within tolerance (0 violations, against 1 flag in the small day-30 window), which strengthens the comparison: the pilot arm's gaps are not an artifact of a noisy control.

## 4. What we would change

> Simulation caveat: this is a simulation with synthetic behavior, useful to find failure modes and to size impact, not proof of real-world effect. The changes below target the failure modes the simulation produced; their real-world effect is unproven.

- **Day-1 reliability needs a redesign, not a tuning** (H4 kill path): per the hypothesis's own discipline, drop the backup mechanism as ineffective in its current form and test the day-before confirmation alone, then add a named human call for hires who stay silent. The stable 24.5% across two windows is the evidence.
- **Staff the human decision queue before launch:** 228 SLA breaches in 90 days sizes the queue at roughly 17 escalations per week across 12 units, with the breach-rate alert (documented, not yet wired) watching it.
- **Sign off the refused-data wording before any real candidate is contacted:** 1,368 refusals in 90 days means the DPO-approved wording will be exercised several times a day at pilot volume.
- **Instrument what the simulation cannot measure from day 1 of the real pilot:** 30-day retention, manager hiring hours, CSAT and escalation acknowledgment latency. The day-90 gate is undecidable without them, and three of its seven targets are currently unmeasurable.
- **Fix the report generator's window wording:** the auto-generated decision strings in `docs/pilot-sim-day90.json` say "in 30 simulated days" regardless of window length (hard-coded in `evals/pilot.py`); the counts are correct, the unit label is not. A one-line code fix before the next run.

## 5. Go/no-go recommendation

> Simulation caveat: this is a simulation with synthetic behavior, useful to find failure modes and to size impact, not proof of real-world effect. This recommendation is conditional on simulated evidence and says so; it is not a proof of real-world effect.

**Recommendation: conditional GO to prepare the summer expansion, with an explicit fix gate before any Wave 2 restaurant goes live.** The charter's day-90 decision (scale to summer campaign / extend / stop) lands in March, when summer hiring starts ("ese mes lo decide todo"). The simulated evidence supports continuing to prepare: the speed thesis held end to end (TTFPS proxy 6.33 vs 27.3 days; contact 100% at 0 minutes), the cost thesis holds trivially, the guardrails that were measurable stayed green at full volume, and the control arm now reproduces discovery cleanly, so the comparison is sound. It does not support scaling yet: the one target the simulation could test and fail (day-1 no-show, 24.5% against the under-8% target) failed at both windows, and retention, manager hours and coverage, three of the seven day-90 targets, are unmeasurable in simulation.

**Conditions for expansion (each must be evidenced, in this order):**

1. **Fix gate, day-1 show:** the H4 kill path is executed (confirmation alone, then the human call for silent hires), and either a fresh simulation with the revised mechanism or early real-pilot data shows day-1 no-show under 8% with at least 100 hires.
2. **Decision queue:** a named owner at the size the run implies (roughly 17 breaches per week across 12 units) and the breach-rate alert wired.
3. **Measurement:** retention, manager hours, CSAT and escalation latency instrumented from day 1 of the real pilot; the day-90 gate is undecidable without them.
4. **Compliance preconditions:** DPIA signed before the first real candidate is contacted (charter guardrail), refused-data wording signed by the DPO, and the erasure tombstone gap in `docs/runbook.md` closed or accepted by the DPO.
5. **Provenance sign-off:** the steering committee accepts this run's provenance (section header) or commissions its own rerun of the same deterministic command.

**If the fix gate fails at the next checkpoint:** extend the pilot one remediation sprint (the charter's day-30 fix path) rather than stopping: the failure mode is operational and concentrated in one mechanism, and the rest of the evidence is directionally positive. Stop triggers remain the charter's: any GDPR incident, or fairness parity red at the Phase 5 interim check.

## 6. Limits of this readout

> Simulation caveat: this is a simulation with synthetic behavior, useful to find failure modes and to size impact, not proof of real-world effect.

- The candidate side is synthetic: personas, hidden reliability and arrival rates are modelled, not measured. The persona pool's hidden reliability was drawn for evaluation coverage, not calibrated to the client's applicant pool, so the absolute day-1 show rate is not directly comparable to the baseline; the relative stability of the rate across windows is the more robust signal.
- The manager side is scripted: approvals are instant, interviews are always attended, documents complete on request. The pilot arm cannot reproduce the human bottlenecks discovery found, which is why the interview show-rate row is marked "not evidenced" rather than "met".
- The control arm is a statistical model of the as-is funnel sampled from `discovery/funnel-baseline.md`, labelled as a model throughout, not a run of real code.
- Retention, manager hours, coverage, CSAT and escalation latency are not produced by the simulation at any day count; they are real-pilot measurements and are named as conditions, not results.
- The artifact's provenance is disclosed in the header: this worker's own run timed out, and the completed JSON came from a concurrent run on the shared worktree. Determinism and the consistency checks make the counts safe to use, but first-hand provenance requires a rerun.
- What this readout is for: to size impact, force the client decisions above, and give the steering committee an honest evidence base with its gaps named, before a real candidate is contacted.
