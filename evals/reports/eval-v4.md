# Eval report eval-v4

Suite `full`, seed 42, 44 personas, judge `scripted-judge/v0`, generated 2026-10-22T20:29:45+00:00.

## Summary

Compared against the previous version `v3`.

| metric | eval-v4 | eval-v3 | delta |
| --- | --- | --- | --- |
| task_success_rate | 1.0 | 1.0 | +0 |
| deterministic_failures | 0 | 0 | +0 |
| interview_show_rate | 1.0 | 1.0 | +0 |
| day1_show_rate | 0.9230769230769231 | 0.9230769230769231 | +0 |
| median_ttfps_hours | 151.99999884555555 | 151.99999885277776 | -7.222e-09 |
| total_cost_usd | 0.082542 | 0.102684 | -0.02014 |
| cost_per_hired_usd | 0.002116 | 0.002633 | -0.000517 |
| mean_judge_score | 3.018 | 3.05 | -0.032 |

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
| 1 | P017 | 1.80 | `eval-p017-eed5ce08ac` | stops_replying/mixed |
| 2 | P038 | 1.80 | `eval-p038-46e07a87f9` | applies_twice/es |
| 3 | P005 | 2.00 | `eval-p005-cbfa81f972` | rude/en |
| 4 | P001 | 2.20 | `eval-p001-ee5371e371` | stops_replying/es |
| 5 | P013 | 2.20 | `eval-p013-e80ef1be4e` | late_20h/pt |

## Task success

44 of 44 personas reached their ground-truth end state (100%).

| persona | expected | achieved | detail |
| --- | --- | --- | --- |
| P001 | graceful_dropout | yes | end states ['matched'] |
| P002 | forward | yes | reached ready_for_rota |
| P003 | escalated | yes | escalation via ['manager_decision_escalate'] |
| P004 | forward | yes | reached ready_for_rota |
| P005 | forward | yes | reached ready_for_rota |
| P006 | forward | yes | reached ready_for_rota |
| P007 | forward | yes | reached ready_for_rota |
| P008 | graceful_dropout | yes | end states ['matched'] |
| P009 | forward | yes | reached ready_for_rota |
| P010 | forward | yes | reached ready_for_rota |
| P011 | escalated | yes | escalation via ['manager_decision_escalate'] |
| P012 | forward | yes | reached ready_for_rota |
| P013 | forward | yes | reached ready_for_rota |
| P014 | forward | yes | reached ready_for_rota |
| P015 | forward | yes | reached ready_for_rota |
| P016 | graceful_dropout | yes | end states ['matched'] |
| P017 | graceful_dropout | yes | end states ['matched'] |
| P018 | forward | yes | reached ready_for_rota |
| P019 | forward | yes | reached ready_for_rota |
| P020 | escalated | yes | escalation via ['manager_decision_escalate'] |
| P021 | forward | yes | reached ready_for_rota |
| P022 | forward | yes | reached ready_for_rota |
| P023 | forward | yes | reached ready_for_rota |
| P024 | forward | yes | reached ready_for_rota |
| P025 | graceful_dropout | yes | end states ['matched'] |
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

- agent turns: 166 across 44 conversation(s)
- tokens: 154536 in / 12955 out
- total USD: 0.0825 (scripted model priced at the gpt-4.1-mini proxy rate)
- hires (offer accepted): 39
- cost per hired candidate: 0.00 USD
- p95 agent latency: 0.06 ms

## What changed

## Iteration 3: consent captured before the reply to the ask

- **Date:** 2025-03-05
- **Baseline:** eval-v3 (seed 42, full suite) and the observed gap recorded
  in odd/tasks/iteration-3.md (eval-p001, eval-p006, eval-p013 and every
  other transcript: the consent ask twice in a row).

### Observe

Reading the eval-v3 transcripts with an exact match over the consent-ask
wording of both scripted sources, the single largest remaining deterministic
gap against G2 (consent captured with notice version, ask never repeated):
88 agent consent asks across the 44 conversations, 2 per conversation, so
every conversation asked twice (fast-suite subset: 20 asks over 10
conversations). The candidate answers the first contact's ask and the next
agent message asks again before moving to screening. Root cause found in
code, one layer: `evals/run.py::_scripted_reply` composes the reply from
`_current_state`. The HireDesk webhook sends the first contact (the consent
ask) without capturing consent, so on the candidate's first reply the
application is still in `contacted`; the scripted reply for
`("new", "contacted")` emits the consent ask again and only its own
`capture_consent` tool call records the consent. The candidate sees the same
ask twice: once from the webhook, once from the agent turn that captures it.

### Hypothesize

We believe dispatching the candidate's consent from the outstanding ask
before composing the reply (so the ask is emitted only while no consent
record exists, and a reply to an outstanding ask captures consent first)
will reduce duplicate consent asks in the transcript from 44 to 0 and raise
the judge's warmth and clarity on the affected conversations, because
evidence E: the only source of the duplicate ask is the
`("new", "contacted")` branch composing before its own `capture_consent`
tool call runs, and every affected transcript shows exactly one duplicate.

### Change

One thing: consent capture precedes reply composition on the reply to an
outstanding ask.

- `evals/run.py::drive_conversation`: when a persona reply arrives while a
  consent ask is outstanding (state `contacted`, no `Consent` row),
  `_capture_outstanding_consent` dispatches `candidate_consents` through the
  core (candidate actor, the real `contacted` to `consented` transition with
  its `consent_notice_shown` guard) and stores the `Consent` row (channel,
  purpose, notice version, simulated timestamp) before the agent composes
  its next message.
- `evals/run.py::_scripted_reply`: the consent ask is composed only while no
  consent record exists; once consent is stored the conversation moves on.
- As before (the `capture_consent` tool path), the scripted eval treats the
  candidate's first reply as the consent reply regardless of its wording,
  and the tool allow-list and the `capture_consent` tool behaviour are
  untouched (`app/agents/services.py` unchanged).

No message copy changes in this iteration.

### Measure

Runner: `uv run python -m evals.run --suite <suite> --seed 42 --label v4`.

- Duplicate consent asks (exact consent-ask match over the stored
  transcripts, eval-v3.json vs eval-v4.json): 88 asks in 44 conversations
  (44 duplicates) to 44 asks in 44 conversations (0 duplicates); fast
  subset 20 asks over 10 conversations to 10 (one per conversation, the
  webhook first contact). In both v4 runs (fast and full) the duplicate
  count is 0.
- Fast suite (10 personas): deterministic failures 0. Full suite (44
  personas): deterministic failures 0, every check 44/44.
- Task success 44/44 and day-1 show rate 0.923 unchanged. Cost per hired
  candidate 0.002633 to 0.002116 USD: one scripted agent turn fewer per
  conversation, because consent capture no longer costs a dedicated turn.
- Judge mean 3.050 (v3) to 2.845 and 2.846 across two v4 full runs of the
  same code and seed; clarity 2.909 to 2.636, warmth 3.205 to 3.000. Not
  decision-grade: ScriptedJudge scores are deterministic digests keyed by
  conversation id, and removing one agent turn changes the conversation
  shape those digests read (the same harness property iterations 1 and 2
  recorded), so the run-to-run variation is wider than the effect.
- RED evidence: against the pre-fix code,
  tests/test_consent_ask_once.py found 2 consent asks per scripted journey
  for both the instant and the late_20h persona (the second ask after the
  candidate had already answered); the first ask was already the first
  outbound message, so the duplicate was the only violation.

### Decision

**Keep.** The deterministic metric is exact: duplicate consent asks went
from 44 conversations in eval-v3 to 0 in eval-v4, with deterministic
failures at 0, task success and day-1 show rate unchanged, and consent now
captured before any processing continues (G2: exactly one `Consent` row,
with the notice version, per conversation). The judge numbers are reported
but not the basis of the decision (noise, see above). Reverting is not
justified: no message copy changed, the tool allow-list and the
`capture_consent` tool behaviour are pinned unchanged, and the only
behavioural delta is that the ask is emitted once and consent is captured
on the reply that answers it.

Next candidate for iteration-4: three questions per message, the screening
message asks three questions at once (work permit, age, commute), which the
judge scores low on brevity and clarity; candidate: split screening into
one question per message.

Also observed this iteration, outside the one-change rule: the live WhatsApp
webhook path has the same shape (it maps consent keywords deterministically);
scoping note in odd/tasks/iteration-3.md, a named follow-up if the same
duplication appears there, not a second change in this iteration.
