# Eval report eval-v1

Suite `full`, seed 42, 44 personas, judge `scripted-judge/v0`, generated 2026-10-22T12:26:01+00:00.

## Summary

Compared against the previous version `vfast`.

| metric | eval-v1 | eval-vfast | delta |
| --- | --- | --- | --- |
| task_success_rate | 1.0 | 1.0 | +0 |
| deterministic_failures | 0 | 0 | +0 |
| interview_show_rate | 1.0 | 1.0 | +0 |
| day1_show_rate | 0.9230769230769231 | 0.875 | +0.04808 |
| median_ttfps_hours | 151.9999988526389 | 151.99999884222223 | +1.042e-08 |
| total_cost_usd | 0.102684 | 0.022373 | +0.08031 |
| cost_per_hired_usd | 0.002633 | 0.002797 | -0.000164 |
| mean_judge_score | 2.768 | 2.66 | +0.108 |

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

## Worst 5 conversations

Lowest mean judge score first; every trace is replayable in the console.

| # | persona | judge mean | trace | label |
| --- | --- | --- | --- | --- |
| 1 | P001 | 1.20 | `eval-p001-c32728ef2c` | stops_replying/es |
| 2 | P042 | 1.40 | `eval-p042-c67a3d0762` | rude/pt |
| 3 | P036 | 1.60 | `eval-p036-a9aa06b75f` | many_questions/mixed |
| 4 | P044 | 1.60 | `eval-p044-d365aa8c4b` | late_20h/pt |
| 5 | P009 | 2.00 | `eval-p009-de1957fb25` | applies_twice/mixed |

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

no iteration log found at docs\iteration-log.md; fill it to record the hypothesis behind this version
