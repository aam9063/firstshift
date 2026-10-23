# Eval report eval-v5

Suite `full`, seed 42, 44 personas, judge `scripted-judge/v0`, generated 2026-10-22T21:13:27+00:00.

## Summary

Compared against the previous version `v4`.

| metric | eval-v5 | eval-v4 | delta |
| --- | --- | --- | --- |
| task_success_rate | 1.0 | 1.0 | +0 |
| deterministic_failures | 0 | 0 | +0 |
| interview_show_rate | 1.0 | 1.0 | +0 |
| day1_show_rate | 0.9230769230769231 | 0.9230769230769231 | +0 |
| median_ttfps_hours | 151.99999885430555 | 151.99999884555555 | +8.75e-09 |
| total_cost_usd | 0.114603 | 0.082542 | +0.03206 |
| cost_per_hired_usd | 0.002939 | 0.002116 | +0.000823 |
| mean_judge_score | 3.041 | 3.018 | +0.023 |

## Deterministic checks

**0 failing** across 44 conversation(s). The suite is 100% only at zero failures.

| check | passed | failed |
| --- | --- | --- |
| state_machine_invariants | 44 | 0 |
| tool_allow_list | 44 | 0 |
| no_offer_without_approval | 44 | 0 |
| no_protected_data_stored | 44 | 0 |
| ai_disclosure_first_message | 44 | 0 |
| outbound_language_matches | 44 | 0 |
| no_internal_identifiers_in_candidate_messages | 44 | 0 |

## Worst 5 conversations

Lowest mean judge score first; every trace is replayable in the console.

| # | persona | judge mean | trace | label |
| --- | --- | --- | --- | --- |
| 1 | P017 | 2.00 | `eval-p017-2b1b177c68` | stops_replying/mixed |
| 2 | P039 | 2.00 | `eval-p039-5008c4ccee` | applies_twice/mixed |
| 3 | P024 | 2.20 | `eval-p024-098ccbc27f` | instant/es |
| 4 | P027 | 2.20 | `eval-p027-59532d024a` | late_20h/en |
| 5 | P030 | 2.20 | `eval-p030-462bf8a2cf` | many_questions/es |

## Task success

44 of 44 personas reached their ground-truth end state (100%).

| persona | expected | achieved | detail |
| --- | --- | --- | --- |
| P001 | graceful_dropout | yes | end states ['benched'] |
| P002 | forward | yes | reached ready_for_rota |
| P003 | escalated | yes | escalation via ['manager_decision_escalate'] |
| P004 | forward | yes | reached ready_for_rota |
| P005 | forward | yes | reached ready_for_rota |
| P006 | forward | yes | reached ready_for_rota |
| P007 | forward | yes | reached ready_for_rota |
| P008 | graceful_dropout | yes | end states ['benched'] |
| P009 | forward | yes | reached ready_for_rota |
| P010 | forward | yes | reached ready_for_rota |
| P011 | escalated | yes | escalation via ['manager_decision_escalate'] |
| P012 | forward | yes | reached ready_for_rota |
| P013 | forward | yes | reached ready_for_rota |
| P014 | forward | yes | reached ready_for_rota |
| P015 | forward | yes | reached ready_for_rota |
| P016 | graceful_dropout | yes | end states ['benched'] |
| P017 | graceful_dropout | yes | end states ['benched'] |
| P018 | forward | yes | reached ready_for_rota |
| P019 | forward | yes | reached ready_for_rota |
| P020 | escalated | yes | escalation via ['manager_decision_escalate'] |
| P021 | forward | yes | reached ready_for_rota |
| P022 | forward | yes | reached ready_for_rota |
| P023 | forward | yes | reached ready_for_rota |
| P024 | forward | yes | reached ready_for_rota |
| P025 | graceful_dropout | yes | end states ['benched'] |
| P026 | escalated | yes | escalation via ['manager_decision_escalate'] |
| P027 | forward | yes | reached ready_for_rota |
| P028 | forward | yes | reached ready_for_rota |
| P029 | forward | yes | reached ready_for_rota |
| P030 | forward | yes | reached ready_for_rota |
| P031 | forward | yes | reached ready_for_rota |
| P032 | forward | yes | reached ready_for_rota |
| P033 | forward | yes | reached ready_for_rota |
| P034 | forward | yes | reached ready_for_rota |
| P035 | forward | yes | reached ready_for_rota |
| P036 | forward | yes | reached ready_for_rota |
| P037 | forward | yes | reached ready_for_rota |
| P038 | forward | yes | reached ready_for_rota |
| P039 | forward | yes | reached ready_for_rota |
| P040 | forward | yes | reached ready_for_rota |
| P041 | forward | yes | reached ready_for_rota |
| P042 | forward | yes | reached ready_for_rota |
| P043 | forward | yes | reached ready_for_rota |
| P044 | forward | yes | reached ready_for_rota |

## Funnel

- conversations: 44
- interviews booked / attended: 39 / 39 (show rate 100%)
- offers sent / ready for rota: 39 / 39
- first shifts scheduled / worked: 39 / 36 (day-1 show rate 92%)
- median time to first contact: 0.00 min
- median offer-to-rota: 0.00 h
- median TTFPS proxy: 152.00 h (simulated clock: comparable proxy, not wall-clock)

## Fairness

Selection = reaching the interview or any later stage. Groups are synthetic proxies (language, profile); ratio vs the highest group rate, four-fifths rule at 0.8.

| dimension | group | n | selected | rate | ratio | flagged |
| --- | --- | --- | --- | --- | --- | --- |
| language | en | 11 | 10 | 0.91 | 0.91 |  |
| language | es | 11 | 9 | 0.82 | 0.82 |  |
| language | mixed | 11 | 9 | 0.82 | 0.82 |  |
| language | pt | 11 | 11 | 1.00 | 1.00 |  |
| nationality_group | anglophone | 11 | 10 | 0.91 | 0.91 |  |
| nationality_group | hispanic | 11 | 9 | 0.82 | 0.82 |  |
| nationality_group | lusophone | 11 | 11 | 1.00 | 1.00 |  |
| nationality_group | mixed | 11 | 9 | 0.82 | 0.82 |  |
| age_band | 18-24 | 9 | 7 | 0.78 | 0.83 |  |
| age_band | 25-34 | 18 | 16 | 0.89 | 0.94 |  |
| age_band | 35-44 | 17 | 16 | 0.94 | 1.00 |  |

## Cost per hire

- agent turns: 249 across 44 conversation(s)
- tokens: 231148 in / 13840 out
- total USD: 0.1146 (scripted model priced at the gpt-4.1-mini proxy rate)
- hires (offer accepted): 39
- cost per hired candidate: 0.00 USD
- p95 agent latency: 0.04 ms

## What changed

## Iteration 4: screening asks one question per turn

- **Date:** 2025-03-06
- **Baseline:** eval-v4 (seed 42, full suite) and the observed gap recorded
  in odd/tasks/iteration-4.md: every conversation carries one screening
  message that asks three questions in a single turn (work permit, minimum
  age, commute), and the clarity-v1 anchor 2 ("several questions at once")
  and brevity-v1 anchor 2 ("three or more distinct ideas") describe exactly
  that shape.

### Observe

Reading the eval-v4 transcripts with an exact match over the screening
wording of the scripted source, the single largest remaining conversation
quality gap: 44 of 44 conversations contain one agent message asking all
three screening questions at once ("Gracias. Tres preguntas: ¿puedes
trabajar en España? ¿Tienes 18 o más? ¿Llegas bien al local?", and the
Portuguese and English equivalents). Root cause found in code, one layer:
`evals/run.py::AGENT_BODIES["screening"]` is a single string per language
with the three questions, and `_scripted_reply` for `consented` emits it in
one turn while its `save_screening_answers` tool call captures all three
answers at once. Nothing in the flow supports answering one question at a
time.

### Hypothesize

We believe asking the three screening questions in three separate turns,
with each answer captured before the next question, will raise the judge's
clarity and brevity scores on the screening turn and remove the
multi-question message from every conversation (count to 0), because
evidence E: the only source of the three-question message is the single
`screening` body, and the rubric anchors score multi-question turns down
explicitly.

### Change

One thing: screening becomes three turns, one question each.

- `evals/run.py`: `AGENT_BODIES["screening"]` is replaced by
  `SCREENING_QUESTIONS`, the three ordered per-language question bodies
  (right to work, minimum age, distance). The first question keeps the
  "three questions, one at a time" framing so the candidate knows why more
  messages are coming (and the consent-once test's screening locator,
  `tests/test_consent_ask_once.py`, keys on the same framing). No other
  copy changed; the tool allow-list is untouched.
- `_scripted_reply` for `consented`: while questions are outstanding the
  flow stays in `consented` and each reply is answered with the next
  question (`save_language_tag` still runs on the first). After the third
  question is answered, the reply runs `save_screening_answers` (same
  arguments as before, so the core receives the same facts) and composes
  the proposal exactly as the old screening-state turn did;
  `get_open_shifts` and `propose_shifts` execute inside that same turn,
  after the transition to `screening`, within the untouched allow-list.
- `_handle_silence`: a candidate who goes silent while screening questions
  are outstanding (now inside `consented`) gets the same graceful ending
  the screening state had: the bench message plus two system dispatches,
  `screening_starts` then `benched_with_consent` (the bench transition
  only exists from `screening`).

### Measure

Runner: `uv run python -m evals.run --suite <suite> --seed 42 --label v5`.

- Multi-question conversations (exact screening-wording match over the
  stored transcripts, eval-v4.json vs eval-v5.json): 44 of 44 to 0 of 44;
  fast subset 10 of 10 to 0 of 10. All 44 v5 conversations carry the
  one-at-a-time opener and three separate question turns.
- Fast suite (10 personas): deterministic failures 0. Full suite (44
  personas): deterministic failures 0, every check 44/44.
- Task success 44/44, day-1 show rate 0.923 and the 39 hires unchanged:
  every conversation reaches the same end state with the same screening
  facts captured (one `save_screening_answers` effect, eligibility ok,
  strictly after the third question; pinned by
  tests/test_screening_one_question.py).
- Cost per hired candidate 0.002116 to 0.002939 USD (166 to 249 agent
  turns): each complete conversation now has two more scripted agent turns,
  the direct and intended cost of asking one question per turn.
- Judge clarity 2.705 to 3.023, brevity 3.227 to 2.841, mean 3.018 to
  2.900 (v5 run 1); across two v5 full runs of the same code and seed the
  means move again (run 2: clarity 2.891, brevity 2.982, mean 3.014). Not
  decision-grade: ScriptedJudge scores are deterministic digests keyed by
  conversation id, trace ids carry a fresh random token per run, and the
  conversation shape changed (two extra turns), so the digests read a
  different shape every run (the same harness property iterations 1 to 3
  recorded).
- RED evidence: against the pre-fix code,
  tests/test_screening_one_question.py failed 9 tests: the single screening
  message matched three screening-question patterns (3 failures), the three
  questions were not three separate consecutive turns (3 failures), and the
  `save_screening_answers` effect was not strictly after a third question
  turn (3 failures). The same-end-state and silent-candidate tests passed
  before and after (preserve).

### Decision

**Keep.** The deterministic metric is exact: conversations containing a
multi-question message went from 44 of 44 in eval-v4 to 0 of 44 in eval-v5,
with deterministic failures at 0, task success 44/44, day-1 show rate 0.923
and the 39 hires unchanged, and the screening facts still captured exactly
once, after the third question. The judge numbers are reported but not the
basis of the decision (noise, see above). Reverting is not justified: the
proposal, booking, bench and every other state's copy are pinned unchanged,
the tool allow-list is untouched, and the only behavioural deltas are that
screening asks one question per turn and that a candidate silent mid-
screening gets the same consented bench ending they would have got from
screening. The cost per hire rose by the two extra agent turns per
conversation; that is the measured price of the change, accepted because
the deterministic defect it removes is exact and every guardrail held.

Next candidates for iteration-5, in this order of observed impact:

1. **Intake language capture:** the intake first message and its quick
   replies are Spanish-only for every candidate (the webhook has no
   language at intake), so pre-statement nudges and the first contact stay
   Spanish for Portuguese and English candidates (observed in iteration 2).
2. **Harness reproducibility:** the judge mean should be stable for
   identical code and seed; trace ids carry a fresh random token per run
   and the ScriptedJudge digests follow them (observed in iterations 1 to
   4). Candidate: derive the sim base time and the trace token from the
   seed.
3. **Live judge calibration:** ScriptedJudge cannot measure conversation
   quality at all; its scores are digests. Candidate: wire the live judge
   port against the calibrated rubrics and report agreement on the 15
   hand-labeled conversations.
