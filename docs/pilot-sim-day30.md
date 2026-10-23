# FirstShift simulated pilot: day-30 ops review (Lumbre Burger Group, weeks 1-5)

Simulated window 2025-06-02 to 2025-07-01 (30 days, seed 42, label day30). Pilot arm: 726 applications across the 12 pilot restaurants through the real pipeline (HireDesk webhook, sim runner, timers, state machine, scripted offline model). Control arm: 179 applications across the 3 control restaurants through a statistical model of the as-is process sampled from `discovery/funnel-baseline.md`; the control is a model, not a run of real code. Arrivals carry the summer shape: a linear ramp to 1.4x across the window and a 1.6x weekend uplift. Weekly pilot arrivals: [141, 162, 179, 191, 53].

## Headline numbers

> Simulation caveat: this is a simulation with synthetic behavior, useful to find failure modes and to size impact, not proof of real-world effect. Every number below is a simulated outcome.

| metric | pilot (real pipeline) | control (as-is model) | discovery baseline |
| --- | --- | --- | --- |
| Applications in window | 726 | 179 | 4,500 over 6 months |
| Contact rate | 100% | 58% | 59% |
| Median time to first contact | 0 min | 4.0 days | 3.9 days (brief: 3.8) |
| Interview show rate | 100% | 70% | 62% |
| Day-1 show rate | 76% | 83% | 82% |
| First shifts worked | 497 | 15 | 325 of 4,500 (7.2%) |
| Median days, application to first worked shift (TTFPS proxy) | 6.3 days | 26.4 days | 27.3 |
| Cost per hire | 0.002919 USD agent cost (scripted-model tokens; human cost extra) | 420 EUR human cost, no agent | 420 EUR (brief section 4) |
| Deterministic check failures | 0 of 726 conversations | n/a (model) | n/a |

The TTFPS proxy compares simulated clocks, not wall-clock promises: the pilot arm compresses the scheduling and preboarding waits the design targets (documents pre-collected, Nómina360 creation tracked), which is exactly the gap discovery measured at 5.1 median days.

Control sampling note: at 179 arrivals the 5 percentage-point tolerance is tighter than the sampling noise of the small control window. The model is pinned against the discovery volume (4,500 applications), where it reproduces every baseline within tolerance (see tests/test_pilot_sim.py). This window's flags, kept visible rather than tuned away:

- interview show rate 0.7037 vs baseline 0.62 (tolerance 0.05)

## What went wrong

> Simulation caveat: this is a simulation with synthetic behavior, useful to find failure modes and to size impact, not proof of real-world effect. Failure modes are the ones the simulation actually produced, with counts.

- **day-1 no-show: 156.** Hires whose first shift was scheduled but never worked (hidden reliability below the confirm threshold); the pipeline booked and prepared them and still lost the day.
- **went silent and were benched: 73.** Candidates who stopped replying and hit the graceful endings (48 h bench timer or the no-reply policy); behaviours: stops_replying x73.

Two structural caveats the simulation itself creates: every booked interview is attended (the simulated world confirms attendance, so the 38% interview no-show problem is only visible in the control model), and the persona pool's hidden reliability was drawn for evaluation coverage, not calibrated to the client's applicant pool, so the pilot arm's absolute day-1 show rate is not directly comparable to the baseline.

## Top escalations

> Simulation caveat: this is a simulation with synthetic behavior, useful to find failure modes and to size impact, not proof of real-world effect. Counts come from the persisted audit trail.

| escalation | count | what it means |
| --- | --- | --- |
| `protected_data_refused` | 432 | Candidate volunteered protected data; the agent refused to store it (guardrail G3) and a human may need to follow up |
| `manager_decision_escalate` | 72 | Manager decision SLA breached: the decision reminder and escalation timer fired and a human must decide |

## Fairness

> Simulation caveat: this is a simulation with synthetic behavior, useful to find failure modes and to size impact, not proof of real-world effect. Groups are synthetic proxies (language for the nationality group, profile for the age band); four-fifths rule at 0.8.

| dimension | group | n | selected | rate | ratio | flagged |
| --- | --- | --- | --- | --- | --- | --- |
| language | en | 181 | 161 | 0.89 | 0.97 |  |
| language | es | 182 | 162 | 0.89 | 0.97 |  |
| language | mixed | 181 | 166 | 0.92 | 1.00 |  |
| language | pt | 182 | 164 | 0.90 | 0.98 |  |
| nationality_group | anglophone | 181 | 161 | 0.89 | 0.97 |  |
| nationality_group | hispanic | 182 | 162 | 0.89 | 0.97 |  |
| nationality_group | lusophone | 182 | 164 | 0.90 | 0.98 |  |
| nationality_group | mixed | 181 | 166 | 0.92 | 1.00 |  |
| age_band | 18-24 | 146 | 128 | 0.88 | 0.95 |  |
| age_band | 25-34 | 290 | 267 | 0.92 | 1.00 |  |
| age_band | 35-44 | 290 | 258 | 0.89 | 0.97 |  |

## Decisions needed from the client

Each decision below is traced to a count the simulation produced; nothing here is hypothetical.

- **Marta:** staff the human decision queue before launch: the agent escalates hiring decisions on SLA breach and a human must answer inside restaurant opening hours (evidence: 72 decision SLA breaches fired in 30 simulated days).
- **Marta (with the DPO):** confirm the refused-data wording the DPO signed off in the DPIA: candidates volunteer protected information unprompted and the agent declines to store it every time (evidence: 432 refusals in 30 simulated days).
- **Raul:** approve a day-1 confirmation policy: a WhatsApp confirmation the day before the first shift plus a same-morning fallback, and decide who calls the hires that still go quiet (evidence: 156 simulated hires were scheduled, prepared and still did not show up on day 1).
- **Marta:** approve the nudge cadence and the bench reuse rule: silence is the normal case, not the exception, and the bench only has value if managers actually call it (evidence: 73 candidates went silent mid-process and were benched by the timers).

## Limits of this simulation

Simulation caveat: this is a simulation with synthetic behavior, useful to find failure modes and to size impact, not proof of real-world effect.

- The candidate side is synthetic: personas, hidden reliability and arrival rates are modelled, not measured, and the arrival volume is scaled to the pilot window rather than the six-month discovery dataset.
- The manager side is scripted: approvals are instant, interviews are always attended, and documents complete on request, so the pilot arm cannot reproduce the human bottlenecks discovery found.
- The control arm is a statistical model of the as-is funnel, faithful to the baseline rates within tolerance and labelled as a model throughout; it is not a run of the real code.
- Cohorts arriving late in the window are followed to their terminal state, so late-window outcomes assume the pipeline they met would have run to completion, the same full-maturation caveat the discovery dataset carries.
- What the simulation is for: to find failure modes, size impact, and force the client decisions above before a real candidate is contacted.
