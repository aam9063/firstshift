# Feature: F08 eval-harness

## Header

- **Objective:** stop judging the agents by "looks good in the demo": generate 40+ synthetic personas, run them through the real system with a candidate-simulator agent, measure deterministic checks (must be 100%), task success against persona ground truth, conversation quality with a calibrated LLM judge, fairness parity and cost per hire, and publish evals/reports/eval-v1.md.
- **Status:** implementation complete, one human step outstanding (calibration labels); awaiting review
- **Next step:** F09 iteration-1 after the human labels the calibration worksheet.
- **Branch:** feature/eval-harness (from dev after PR 27 merged).

## Specs

Source of truth: `specs/05-iteration-evals.md` sections 1, 2 and 3. Governing quotes:

- S1 (§1): at least 40 personas generated from a seeded schema covering profile, languages, availability, behaviour (instant reply, 20h late, stops replying, salary first, rude, distressed, injection, volunteers protected info, applies twice); ground truth per persona (which shifts fit, hidden reliability, what makes them drop out); a candidate simulator agent plays each persona through the channel port with its own clock; the system under test must not see the persona file.
- S2 (§2 deterministic): state machine invariants, tool allow-lists per state, no offer without approval, no protected data stored, AI disclosure in first message, language matches candidate; assertions over audit log and stored records; must be 100%.
- S3 (§2 task success): persona reached the correct end state vs persona ground truth.
- S4 (§2 quality): LLM-as-judge with a written versioned rubric, 1-5 per criterion; calibrate on 15 hand-labeled conversations and report agreement.
- S5 (§2 funnel/fairness/cost): simulated metrics computed from the event log; selection-rate ratios by language, nationality group and age band, flag below 0.8; tokens and USD per hired candidate, p95 latency.
- S6 (§3 runner): `uv run python -m evals.run --suite full --seed 42 --label vN` produces evals/reports/eval-vN.md with summary vs previous version, zero-failing deterministic checks, worst 5 conversations by judge score, fairness table, cost per hire, and a "what changed" section; plus a fast suite (10 personas, under 3 minutes).

## Constraints

- Runner is reproducible: seeded personas, seeded clocks, scripted model for the system under test (deterministic); the judge may use a model but its outputs are cached per conversation+rubric version so reruns are stable.
- No network in tests except the judge behind a port with a scripted/cached implementation.
- This branch touches evals/, app/ (small hooks if strictly needed), tests/ only. No web/.

## Tasks

| ID | Spec | Task | Status |
|---|---|---|---|
| T1 | S1 | Persona generator (40+, seeded) with ground truth; candidate simulator agent over the channel port | pending |
| T2 | S2 | Deterministic checks over audit log and stored records (must be 100%) | pending |
| T3 | S3,S5 | Task success vs ground truth; funnel metrics from the event log; fairness table; cost/latency | done (41c91d1) |
| T4 | S4 | LLM judge behind a port, versioned rubric, calibration flow with 15 human-labeled conversations and agreement reporting | partial: port, rubrics, calibration CLI and worksheet done; agreement awaits the human labels (T5 checklist) |
| T5 | S6 | Runner CLI, JSON + markdown reports, fast suite; run full suite and publish eval-v1.md | done (41c91d1): fast suite 12.6s, full suite 55.8s, eval-v1 baseline published |

## Open questions

- Judge model in live mode: default to a strong model for judging (env JUDGE_MODEL, fallback OpenAI_MODEL); calibration needs the human to label 15 conversations, which the runner will emit as a labeling worksheet.

## Log

- L1 (user, verbatim): "continuamos"
- L2: PR 27 (dev->main) merged by the user before F08 started; PR 26 auto-merged; dev at 65d54a1.
- L3: Evidence (T1): 44 personas seed 42, axis coverage min 8/11/14/11/4, 36 tests, commit 44025c3.
- L4: Evidence (T2/T4a): 6 deterministic checks with passing+violating fixtures, judge port (ScriptedJudge + offline OpenAI scaffold), 5 versioned rubrics, calibration worksheet/agreement; 45 tests; merged from the eval-judge worktree (6a09c40, merge 7ed857c).
- L5: Evidence (T3/T5): metrics (task success, funnel, fairness 0.8 inclusive, cost/latency), runner CLI, baseline eval-v1 (0 deterministic failures across 44, task success 44/44, fairness lowest 0.82 es and mixed, 0.83 age 18-24, day-1 show 92.3%, 210 agent turns, $0.0026 cost per hire at the scripted proxy rate, p95 latency 0.051 ms scripted). Fast suite 12.6s. Commit 41c91d1.
- L6: T1 defect found by the runner worker and fixed under an approved minimal surface expansion: AVAILABILITY_LINES and RUDE_PREFIXES lacked the 'mixed' language variants, raising KeyError for 8 personas; two RED-first regression tests now pin total coverage.
- L7: Interpreted decisions: interview attendance always confirmed by the sim world (show rate 1.0 by construction, reliability gates the day-1 show); manager approvals also write the Decision row (app has no Decision writer yet) or INV-1 would fail; distressed escalation goes through the real manager-SLA timer; fairness nationality/age groups are deterministic proxies because G3 forbids collecting them; mixed-language personas answer in Spanish.
