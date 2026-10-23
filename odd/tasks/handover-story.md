# Feature: F14 handover-and-story

## Header

- **Objective:** leave the client (and a future engineer) able to run and extend FirstShift without the author, and turn the project into a clear, honest story for an FDE interview.
- **Status:** in progress
- **Branch:** feature/handover-story, from dev (7982a42).

## Specs

Source of truth: `specs/07-handover-and-story.md` sections 1 to 5.

- S1 (§1): `docs/handover.md`: what exists, what is stubbed, what is simulated (one table, no ambiguity); how to run, test, evaluate and deploy in ten commands or fewer; architecture in one diagram plus ADR links; open risks and known limitations ranked; the next three recommended features with expected impact (demand-triggered requisitions, crew referral loop, voice screening); ownership after handover.
- S2 (§2): `docs/case-study.md`, about 800 words, with the seven-part structure: context, what I found (three strongest insights with one piece of evidence each), the reframe, what I built, how I knew it worked (eval and pilot numbers, clearly labelled simulation), what I would do with a real client next, and how I worked (ODD, specs as source, test-first core, one real feature-document excerpt).
- S3 (§3): `docs/demo-video-notes.md`: shot list based on the D1, D4 and D6 flows, English voice-over, captions, final frame with the three headline numbers and the repo link.
- S4 (§4): `docs/interview-narrative.md`: 30-second version, 2-minute STAR version, bridge to the author's real experience, and at least ten likely questions with crisp answers. The bridge must use only details the author confirms; never invent them.
- S5 (§5): the narrative may reference only the public facts listed about the target company and must not claim inside knowledge.
- S6 (README): update `README.md` with results, "What is stubbed" and links.

## Tasks

| ID | Spec | Task | Status |
|---|---|---|---|
| T1 | S1 | handover.md | pending |
| T2 | S2 | case-study.md | pending |
| T3 | S3 | demo-video-notes.md | pending |
| T4 | S4,S5 | interview-narrative.md, with the bridge section marked pending until the author answers | pending |
| T5 | S6 | README results, what-is-stubbed and links | pending |

## Constraints

- Numbers must trace to `evals/reports/`, `docs/pilot-sim-day30.*`, `docs/pilot-sim-day90.*` or the brief; simulations are labelled in every results sentence.
- No invented facts about the author or the target company; the bridge stays a marked placeholder until the author provides the details.
- English, no em dash.

## Log

- L1 (user, verbatim): "todo en dev. continúa"
- L2: dev at 7982a42 (the automated main->dev sync), which proves the sync workflow is live.
- L3: The author's real-experience details for the bridge are requested in the session; the document ships with that section explicitly pending rather than invented.
