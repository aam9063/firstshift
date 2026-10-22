# Eval report eval-v2

Suite `full`, seed 42, 44 personas, judge `scripted-judge/v0`, generated 2026-10-22T17:18:13+00:00.

## Summary

Compared against the previous version `v1`.

| metric | eval-v2 | eval-v1 | delta |
| --- | --- | --- | --- |
| task_success_rate | 1.0 | 1.0 | +0 |
| deterministic_failures | 0 | 0 | +0 |
| interview_show_rate | 1.0 | 1.0 | +0 |
| day1_show_rate | 0.9230769230769231 | 0.9230769230769231 | +0 |
| median_ttfps_hours | 151.99999884888888 | 151.9999988526389 | -3.75e-09 |
| total_cost_usd | 0.102684 | 0.102684 | +0 |
| cost_per_hired_usd | 0.002633 | 0.002633 | +0 |
| mean_judge_score | 3.009 | 2.768 | +0.241 |

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
| 1 | P003 | 2.00 | `eval-p003-f68a16c8ab` | distressed/mixed |
| 2 | P017 | 2.00 | `eval-p017-a947b5e1ba` | stops_replying/mixed |
| 3 | P001 | 2.20 | `eval-p001-618979f8dd` | stops_replying/es |
| 4 | P025 | 2.20 | `eval-p025-447a9f44c6` | stops_replying/es |
| 5 | P026 | 2.20 | `eval-p026-e4d69c96a5` | distressed/es |

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

## Candidates for iteration-2

Picked from the same calibration read; one change per iteration, in this
order of observed impact:

1. **Language drift:** eval-p002 opens in Spanish, switches to Portuguese,
   then sends the offer in Spanish again. Candidate: pin every outbound to
   the candidate's stated preferred language at the reply composer.
2. **Repeated disclosure:** the AI consent ask repeats verbatim after the
   candidate already consented. Candidate: gate the consent ask on stored
   consent state instead of the turn counter.
3. **Three questions per message:** the screening message asks three
   questions at once (work permit, age, commute), which the judge scores
   low on brevity and clarity. Candidate: split screening into one question
   per message.
