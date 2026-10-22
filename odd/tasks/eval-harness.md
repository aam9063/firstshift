# Feature: F08 eval-harness

## Header

- **Objective:** stop judging the agents by "looks good in the demo": generate 40+ synthetic personas, run them through the real system with a candidate-simulator agent, measure deterministic checks (must be 100%), task success against persona ground truth, conversation quality with a calibrated LLM judge, fairness parity and cost per hire, and publish evals/reports/eval-v1.md.
- **Status:** in progress
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
| T3 | S3,S5 | Task success vs ground truth; funnel metrics from the event log; fairness table; cost/latency | pending |
| T4 | S4 | LLM judge behind a port, versioned rubric, calibration flow with 15 human-labeled conversations and agreement reporting | pending |
| T5 | S6 | Runner CLI, JSON + markdown reports, fast suite; run full suite and publish eval-v1.md | pending |

## Open questions

- Judge model in live mode: default to a strong model for judging (env JUDGE_MODEL, fallback OpenAI_MODEL); calibration needs the human to label 15 conversations, which the runner will emit as a labeling worksheet.

## Log

- L1 (user, verbatim): "continuamos"
- L2: PR 27 (dev->main) merged by the user before F08 started; PR 26 auto-merged; dev at 65d54a1.
