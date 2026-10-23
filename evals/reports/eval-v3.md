# Eval report eval-v3

Suite `full`, seed 42, 44 personas, judge `scripted-judge/v0`, generated 2026-10-22T19:42:06+00:00.

## Summary

Compared against the previous version `v2`.

| metric | eval-v3 | eval-v2 | delta |
| --- | --- | --- | --- |
| task_success_rate | 1.0 | 1.0 | +0 |
| deterministic_failures | 0 | 0 | +0 |
| interview_show_rate | 1.0 | 1.0 | +0 |
| day1_show_rate | 0.9230769230769231 | 0.9230769230769231 | +0 |
| median_ttfps_hours | 151.99999885277776 | 151.99999884888888 | +3.889e-09 |
| total_cost_usd | 0.102684 | 0.102684 | +0 |
| cost_per_hired_usd | 0.002633 | 0.002633 | +0 |
| mean_judge_score | 3.05 | 3.009 | +0.041 |

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
| 1 | P028 | 1.40 | `eval-p028-10b836d81b` | volunteers_protected_info/en |
| 2 | P031 | 1.60 | `eval-p031-1a30f928bd` | many_questions/pt |
| 3 | P027 | 2.00 | `eval-p027-a8117658f5` | late_20h/en |
| 4 | P041 | 2.00 | `eval-p041-bfc46cf642` | instant/mixed |
| 5 | P011 | 2.20 | `eval-p011-a35a36a6a6` | distressed/en |

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

- agent turns: 210 across 44 conversation(s)
- tokens: 195121 in / 15397 out
- total USD: 0.1027 (scripted model priced at the gpt-4.1-mini proxy rate)
- hires (offer accepted): 39
- cost per hired candidate: 0.00 USD
- p95 agent latency: 0.05 ms

## What changed

## Iteration 2: language-aware candidate-facing copy

- **Date:** 2025-03-04
- **Baseline:** eval-v2 (seed 42, full suite) and the calibration read that
  named language drift as the second defect (eval-p002: opens in Spanish,
  switches to Portuguese, receives the offer in Spanish again).

### Observe

Reading eval-v2 with the exact-body method over the stored transcripts, the
single largest remaining deterministic gap against C-O4 (language matches
candidate): 25 outbound candidate-facing messages across 21 of 44
conversations were in Spanish while the candidate had stated Portuguese or
English (21 offers, 4 nudges). Root cause found in code, two layers:

1. The seven candidate-facing templates (offer, nudge_1, nudge_2,
   interview_reminder, bench_offer, bench_reengagement, rejection) exist only
   in Spanish in both dispatch dictionaries (`app/services/scripted.py::
   _SCRIPTED_BODIES` and the `app/sim/dispatch.py` resolution into it).
2. `evals/run.py` built the core snapshot with `language="es"` for every
   persona, and the canned outbox bodies carried no language tag at all, so
   the `outbound_language_matches` guardrail had nothing to compare for them:
   it passed without measuring anything (proven vacuous by a RED test).

The agent-loop replies were already language-aware; the drift comes from the
canned copy and the invisible tags.

### Hypothesize

We believe resolving every candidate-facing template from the candidate's
stated preferred language (es/pt/en, Spanish only as the documented last
resort when the language is genuinely unknown) and carrying the persona's
language into the core snapshot will reduce outbound messages whose language
differs from the candidate's stated language from 25 to 0 (the 21
post-statement drifts to 0) and keep deterministic failures at 0 with the
language guardrail now non-vacuous, because evidence E: both remaining
sources of Spanish-only candidate copy are the two dispatch dictionaries, and
the hardcoded snapshot language plus the untagged canned bodies are the reason
the guardrail never caught them.

### Change

One thing: language-aware candidate-facing copy, end to end.

- Per-language variants (es/pt/en) of the seven candidate-facing templates in
  both dispatch paths, resolved from `candidate.preferred_language`; Spanish
  is the documented last resort only when the language is unknown or
  unsupported. The variants keep the meaning of the Spanish originals, stay
  WhatsApp-sized and add no promises. Portuguese and English copy is authored
  in this iteration; its tone review is a human task.
- Both dispatch paths tag candidate-facing outbound with the resolved
  language (message.out payload and outbox row): the instrumentation, not a
  second behaviour change.
- `evals/run.py` carries the persona's language into the core snapshot
  instead of the literal `"es"`.
- The guardrail is non-vacuous: after the candidate's first inbound message,
  a candidate-facing body must carry a language tag equal to the stated
  preference; untagged or mismatched is a violation. Messages sent before the
  candidate first spoke (the intake first message, timer nudges while
  unanswered) use the intake default and cannot contradict a preference not
  yet stated.
- Internal-recipient bodies from iteration-1 (decision_request,
  decision_reminder, decision_escalation, no_show, interview_reoffer,
  backup_activate) are not candidate-facing and are unchanged.

### Measure

Runner: `uv run python -m evals.run --suite <suite> --seed 42 --label v3`.

- Drift count (exact template-body match over the stored transcripts,
  eval-v2.json vs eval-v3.json): 25 to 4 drift messages across the full
  suite; post-statement drift 21 to 0. The 4 remaining are `nudge_1` fired
  before the persona's first reply (late_20h personas P010, P013, P027,
  P044): the candidate had not stated a language yet, so the intake default
  applied, and the non-vacuous guardrail tolerates exactly that case.
- Fast suite (10 personas): deterministic failures 0. Full suite (44
  personas): deterministic failures 0, `outbound_language_matches` 44/44
  passed with the check now verifying tags on every candidate-facing body.
- Judge mean 2.945 to 3.036 across two v3 full runs of identical code and
  seed (2.945, then 3.036); language score by stated language es 2.545 to
  3.045, pt 2.636 to 3.182, en 2.909 to 3.455. Not decision-grade:
  ScriptedJudge scores are deterministic digests keyed by conversation id and
  trace ids carry a fresh random token per run, so the run-to-run variation
  is wider than the effect (the same harness property iteration-1 recorded).
- Task success 44/44, day-1 show rate 0.923 and cost per hire 0.002633 USD
  all unchanged.
- RED evidence: against the pre-fix code, both dispatch paths returned the
  Spanish offer body for Portuguese and English candidates (six copy tests
  failed), and the language guardrail passed on an untagged Spanish offer
  body sent to a Portuguese candidate (vacuous, observed via
  tests/test_language_copy.py).

### Decision

**Keep.** The deterministic metric is exact: post-statement language drift
went from 21 messages in 21 conversations in eval-v2 to 0 in eval-v3, with
deterministic failures at 0 and the guardrail now measuring the candidate's
real stated language instead of passing vacuously. Task success, day-1 show
rate and cost per hire are unchanged. The 4 remaining pre-statement nudges
are the designed intake default, not drift; removing them would require the
webhook to capture language at intake, which is a different change. The judge
numbers are reported but not the basis of the decision (noise, see above).
Reverting is not justified: PRESERVE tests pin the Spanish originals for es
candidates and the unchanged internal-recipient bodies, and the only
behavioural delta is that candidate-facing copy follows the stated language.

Next candidates for iteration-3, in this order of observed impact:

1. **Repeated disclosure:** the AI consent ask repeats verbatim after the
   candidate already consented. Candidate: gate the consent ask on stored
   consent state instead of the turn counter.
2. **Three questions per message:** the screening message asks three
   questions at once (work permit, age, commute), which the judge scores
   low on brevity and clarity. Candidate: split screening into one question
   per message.

Also observed this iteration, outside the one-change rule: the intake first
message and its quick replies are Spanish-only for every candidate (the
webhook has no language at intake); low priority, it precedes any stated
preference.
