# Metric tree: crew hiring pilot

- **Phase:** 2, problem framing (spec: `specs/02-problem-framing.md` section 3).
- **North star:** Time to first productive shift (TTFPS), exactly as the spec defines it: **median days from application to the end of the first worked shift in which the new hire completed the food hygiene module before starting.**
- **Baselines** come from `specs/00-client-brief.md` section 4 (brief §4) or `discovery/funnel-baseline.md` (funnel). Targets are design commitments for the 90-day pilot, each anchored to an identified mechanism in discovery. Where no baseline exists today, that is stated honestly and the pilot instruments it.

## North star

**TTFPS.**

- **Baseline:** about 27.3 days, the sum of funnel stage medians from application to first worked shift (funnel: 3.9 + 2.0 + 4.3 + 5.0 + 3.1 + 2.4 + 5.1 + 1.5). Today the hygiene module is frequently not done before start: 2 of the trainer's last 5 new hires arrived without having started it [T-iker-08], so the true TTFPS baseline is 27.3 days or worse.
- **Pilot target:** median TTFPS of **14 days or less** by day 90 in the 12 pilot restaurants. Derivation from the funnel stage medians: first contact 3.9 to under 0.1 days (agent replies in minutes, the winning real reply was under an hour [T-candidate-a-10]), screening to offer 2.0 + 4.3 with about half the 5.0-day scheduling wait recovered, offer to first shift 9.5 to under 4 days (documents pre-collected before offer [T-sofia-10], Nómina360 creation tracked daily against its 3-to-6-day range [T-yolanda-20], hygiene module enrolled at opt-in before the interview). Sum of targets: roughly 0.1 + 2.0 + 2.2 + 2.5 + 2.4 + 1.0 + 1.5 + 1.5 = about 13.2 days, rounded to the 14-day commitment.

## The tree

| Branch | Metric | Baseline | Source | Pilot target |
|---|---|---|---|---|
| Speed | Median time to first contact | 3.8 days | brief §4 (funnel: 3.9 days) | Median under 1 hour while the agent is live; 100% of applicants get an answer, including a fast no |
| Speed | Median time, applied to interview scheduled | 4.3 days | funnel | 2 days or less |
| Speed | Median time, offer to on rota | about 7.5 days (sum of funnel medians: offer to documents 2.4, documents to on rota 5.1) | funnel; brief §4 gives 9 days offer to first worked shift | 3 days or less, with the Nómina360 creation tracked per person from offer day |
| Conversion | Contacted rate (share of applicants contacted) | 59.0% | funnel (brief §4: 41% never contacted) | 95% or more |
| Conversion | Interview show rate | 62.0% (38% no-show) | funnel; brief §4 | 80% or more |
| Conversion | Offer acceptance rate | Not captured today: the funnel conflates acceptance with document collection (offer 518 to documents_complete 440, 84.9%) | funnel caveat | Instrumented from week 1; 85% or more of offers accepted within 7 days (a candidate lost a job by waiting a week [T-candidate-c-12]) |
| Conversion | Day-1 show rate | 82.1% (day-1 no-show 17.9%; brief §4: 18%) | funnel; brief §4 | Day-1 no-show under 8% |
| Quality | 30-day retention of pilot hires | 72.0% | funnel (full-maturation steady-state caveat applies) | 80% or more |
| Quality | 90-day retention of pilot hires | 48% retained (brief §4: 52% attrition; consistent with funnel: 156 of 325 day-1 workers) | brief §4; funnel | 60% or more |
| Quality | Manager rating of the hire after week 2 (1 to 5, one WhatsApp question) | Not collected today | none exists | Instrumented from the first pilot hire; median 4.0 or more |
| Effort | Manager minutes per hire | No per-hire measure exists. Proxy: about 6 hours per week per restaurant on hiring; 105 minutes observed on one peak Saturday | brief §4; ride-along counts | Proxy reduced to 2 hours per week or less; per-hire minutes instrumented from week 1 |
| Effort | Talent team touches per hire | Not measured. Context: 3 of 14 recruiters firefight HireDesk, about 1 in 3 applications reviewed | [T-jordi-02, T-jordi-06] | 5 or fewer logged touches per hire |
| Coverage (business outcome) | % of peak hours understaffed (labor below forecast) in pilot restaurants | 7.5% in coastal July and August | brief §4 | 4% or less across the pilot's peak window |

**Measurement note on coverage:** ShiftGrid labor forecasts are overwritten by about half the managers so the screen does not show red, and the Area Director trusts phone calls, not the screen [T-raul-18]. The pilot therefore measures coverage from TillCloud sales at 15-minute granularity against scheduled hours in the ShiftGrid rota, with the method fixed and documented before the pilot starts, not from the overwritten forecast field.

## Guardrail metrics (must not get worse)

| Guardrail | Baseline | Target / rule |
|---|---|---|
| Candidate satisfaction (one-question CSAT at end of conversation) | Not collected today; the CPO's stated nightmare is a rude bot screenshot going public [T-marta-18, T-marta-20] | Median 4.0 or more of 5 from pilot week 2; every score of 1 or 2 reviewed within one business day |
| Fairness parity across age band, nationality and language | No baseline until the Phase 5 evaluation runs | Pass/fail against the parity thresholds defined in Phase 5; reported in every steering review, evaluated before any scale-up decision |
| Escalation rate to humans, handled within SLA | No governed escalation path exists today; today the answer is silence for 41% (funnel) | 95% or more of escalations to a human acknowledged within 30 minutes during restaurant opening hours; the SLA itself is a design rule, fixed before launch |
| GDPR incidents | Today's state is the exposure: candidate data in personal WhatsApp the DPO cannot search [T-laura-12], HireDesk retention forever by default [T-laura-08] | Zero incidents. Precondition: DPIA signed by the DPO before a single candidate is contacted [T-laura-28] |

## Attribution: how we separate FirstShift from the season

- **Design:** 12 pilot restaurants against 3 comparable control restaurants, both in Alicante province, per brief section 6. Comparison is difference-in-differences on the metric tree over the 90 days, which absorbs level differences between units and any season-wide trend.
- **Seasonality risk:** coastal units add 25% to 40% headcount from June to September (brief section 1), and candidates shop six chains in one evening [T-candidate-a-06], so a candidate "lost" by the control unit may be hired by a pilot unit across the street. Spillover between pilot and control is real and will bias the measured gap down, not up.
- **Honest limit:** 3 control units is weak. With n = 3 per arm, unit-level variance dominates; one unusually good or bad manager in the control group moves the comparison more than the intervention. We can state direction and magnitude ranges, not statistical significance.
- **Stronger option we propose:** a staggered rollout inside the pilot window. Activate the 12 units in two waves of 6, four to six weeks apart, with wave 2 running the current process under measurement until its activation date. Every unit then serves as its own control before go-live, the sample for the "after" comparison doubles, and the March summer-hiring wave (which the Area Director calls the month that decides everything [T-raul-28]) hits only units with at least four weeks of live operation. The 3 control units stay as a long-run check on area-wide shocks. We recommend this to the client at the steering kickoff; the contract's 12 + 3 shape (brief section 6) does not change either way.
