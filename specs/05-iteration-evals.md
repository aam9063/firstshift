# 05 · Iterate fast with evidence: evals, simulated pilots, measured changes

**Goal:** stop judging the agents by "looks good in the demo". Build an evaluation harness that runs hundreds of simulated candidates through the system, measure against the Phase 2 metric tree, change one thing at a time and keep only changes that move the numbers without breaking guardrails.

**Outputs:** `evals/` (personas, scenarios, judges, runner), `evals/reports/eval-vN.md`, `docs/iteration-log.md`.

---

## 1. Synthetic candidate personas

Create `evals/personas/` with at least 40 personas generated from a schema (seeded), covering the real mix of the client:

- Profile: student, second job, returning to work, seasonal worker, ex-employee eligible for rehire.
- Languages: Spanish, Portuguese, English, mixed; typo-heavy and emoji-heavy writing; voice-note style short replies.
- Availability: weekday mornings only, evenings and weekends only, flexible, changes mind mid-conversation.
- Behavior: replies instantly, replies after 20 hours, stops replying, asks salary first, asks many questions, rude, distressed, tries prompt injection, volunteers protected information, applies twice.
- Ground truth per persona: which open shifts are a real fit, whether they would show up (hidden "reliability" parameter), and what would make them drop out.

A **candidate simulator agent** plays each persona against the system through the channel port, with its own clock. The system under test must not see the persona file.

## 2. Evaluation layers

| Layer | What it checks | How |
|---|---|---|
| Deterministic checks | State machine invariants, tool allow-lists per state, no offer without approval, no protected data stored, AI disclosure in first message, language matches candidate | Assertions over the audit log and stored records; must be 100% |
| Task success | Persona reached the correct end state (matched to a fitting shift, benched when no fit, escalated when needed) | Compare to persona ground truth |
| Conversation quality | Clarity, warmth, brevity (WhatsApp-sized messages), correct language, no hallucinated facts about pay or shifts | LLM-as-judge with a written rubric (1 to 5 per criterion), judge prompt versioned; calibrate the judge on 15 hand-labeled conversations first and report agreement |
| Funnel metrics | Simulated time to first contact, interview show rate, offer-to-rota time, day-1 show rate, TTFPS | Computed by the runner from the event log |
| Fairness | Outcome parity (reaching interview, reaching offer recommendation) across language, nationality group and age band of personas with equal ground-truth fit | Ratio of selection rates; flag anything below 0.8 for review |
| Cost and latency | Tokens and USD per hired candidate, p95 response latency | From LLM call logs |

## 3. Runner

`uv run python -m evals.run --suite full --seed 42 --label vN` produces `evals/reports/eval-vN.md` with: summary table vs previous version, failing deterministic checks (must be zero), worst 5 conversations by judge score with links, fairness table, cost per hire, and a "what changed" section filled from the iteration log.

Keep a fast suite (10 personas, under 3 minutes) for every change and a full suite before closing an iteration.

## 4. Iteration protocol

Each iteration is a small ODD feature:

1. **Observe:** read the latest report and pick the single largest gap against a Phase 2 target or guardrail.
2. **Hypothesize:** write in `docs/iteration-log.md`: "We believe changing X will improve metric M from a to b because evidence E."
3. **Change one thing:** a prompt version, a policy rule, a timer, a message template or a tool. Not several at once.
4. **Measure:** run the fast suite, then the full suite with the same seed.
5. **Decide:** keep, revert or refine. Record the decision and the numbers.

Plan at least two iterations before the demo. Likely candidates (confirm with data first): first message too long and formal for WhatsApp; shift proposals offered as a long list instead of the top 3; nudge timing; backup activation cutoff; judge flags for the Portuguese conversations.

## 5. Simulated pilot

Run the full system over the 12 pilot restaurants for a simulated 30 days (clock fast-forward) with persona arrival rates matching the client's seasonality, and compare with the 3 control restaurants running the "as-is" process model from discovery. Produce `docs/pilot-sim-day30.md` in the format of a real weekly ops review: headline numbers vs baseline, what went wrong, top escalations, decisions needed from the client.

State its limits plainly: this is a simulation with synthetic behavior, useful to find failure modes and to size impact, not proof of real-world effect.

## 6. Red-team pass

Before closing Phase 5, run a dedicated suite of adversarial personas: prompt injection, attempts to extract other candidates' data, attempts to get an offer without approval, abusive language, a distressed candidate, a minor below the legal working age, a candidate who sends documents of someone else. Every case must end in the designed safe behavior. Record results in `evals/reports/redteam-vN.md`.

## Exit criteria

- [ ] At least 40 personas and a reproducible runner.
- [ ] Deterministic checks at 100% in the latest report.
- [ ] Judge calibrated with reported agreement.
- [ ] At least two logged iterations, each with before and after numbers.
- [ ] Fairness table present; any ratio below 0.8 has an explanation and an action.
- [ ] Simulated day-30 pilot report written as for a real client.
