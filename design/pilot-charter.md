# Pilot charter: FirstShift, crew hiring, Costa Blanca

- **Phase:** 2, problem framing. One page, as the spec requires (`specs/02-problem-framing.md` section 7).
- **Client:** Lumbre Burger Group. **Vendor:** Forward Deployed Engineering team (FirstShift).

## Problem

See `design/problem-statement.md`: the funnel loses candidates at the front door (3.9 median days to first contact, 41.0% never contacted), at the interview (38.0% no-show), and in the unowned hired-to-rota window (5.1 median days, the largest gap, gated by Nómina360's 3-to-6-day creation [T-yolanda-20]). Business consequence: 7.5% of peak hours understaffed in coastal July and August, 52% of new hires gone within 90 days, about 6 manager-hours per week per restaurant on hiring (brief section 4).

## North star

**TTFPS:** median days from application to the end of the first worked shift with the food hygiene module completed before starting. **Baseline:** about 27.3 days (funnel stage medians; true value is worse because 2 of 5 recent hires at the reference unit had not started the module [T-iker-08]). **Pilot target:** 14 days or less by day 90 (derivation in `design/metric-tree.md`).

## Guardrails (any breach pauses rollout, not the pilot itself)

Candidate CSAT median 4.0 or more of 5; fairness parity across age band, nationality and language per the Phase 5 evaluation; 95% or more of human escalations acknowledged within 30 minutes during opening hours; zero GDPR incidents, with the DPIA signed before the first candidate is contacted [T-laura-28].

## Scope

90 days. 12 company-operated restaurants in Alicante province (Costa Blanca) live, 3 comparable restaurants as control (brief section 6). Crew hiring and onboarding through first productive shift, in Spanish first. No franchisees, no new app for managers (WhatsApp quick replies only), no changes to contracts or Social Security registration ownership (see `design/non-goals.md`, `design/constraints.md`).

## Roles

| Side | Who | Responsibility |
|---|---|---|
| Client | Marta Ibáñez (CPO) | Business sign-off, go/no-go, board reporting [T-marta-22] |
| Client | Raúl Sempere (Area Ops) | Names the 12 + 3 units, commits managers, co-owns the coverage metric [T-raul-24] |
| Client | Laura Cebrián (DPO) | DPIA and written approval before any candidate contact; retention and deletion rules [T-laura-28] |
| Client | Hugo Andrade (IT) | Approves write paths, gets monitoring and alerts on every write [T-hugo-22, T-hugo-30] |
| Client | Sofía Marques (People Ops) | Owns Nómina360 registration; validates the document pack flow [T-sofia-04] |
| Client | Jordi Puig (TA) | Validates screening recommendations; every reject stays human-signed [T-jordi-22] |
| Client | Restaurant managers | Act via WhatsApp quick replies; keep and consent-log their bench |
| Vendor | FDE team | Builds and operates the agent layer, integrations and mocks, trains users, runs the measurement plan, reports weekly |

## Decision cadence

- **Weekly ops review, 30 minutes** (Raúl, Sofía or delegate, vendor lead): live metric tree numbers, guardrail status, incidents, escalations, next-week risks. Written summary within 24 hours.
- **Bi-weekly steering** (Marta, Raúl, Laura or delegate, Hugo or delegate, vendor lead): hypothesis progress against kill thresholds, guardrail trends, spend, decisions needed.

## Go / no-go

- **Day 30 (continue / fix / stop):** agent live in 9 or more of 12 units; contacted rate 85% or more and median first contact under 24 hours; interview show rate 70% or more; day-1 no-show at or below baseline (17.9%); all guardrails green; no unremediated Nómina360 write failures (C-T2 to C-T6). Fix path: one remediation sprint. Stop triggers: any GDPR incident, or fairness parity red at the Phase 5 interim check.
- **Day 90 (scale to summer campaign / extend / stop):** TTFPS 14 days or less; contacted rate 95% or more; interview show rate 80% or more; day-1 no-show under 8%; 30-day retention 80% or more; manager hiring time 2 hours per week or less; coverage target on trend (4% or less of peak hours understaffed); all guardrails green; hypotheses H1 to H4 not killed. The scale decision lands in March, when summer hiring starts and "ese mes lo decide todo" [T-raul-28]; the staggered rollout option in the metric tree is decided here if not before.

## Exit plan (if the pilot fails or is not extended)

1. **Stop intake first, then conversations:** agent stops contacting new candidates immediately; open conversations get a human handover message.
2. **Handover to HR:** every open candidate thread, document status and per-hire tracker is exported to People Ops and the area HRBP in a standard format within 10 business days; managers' bench entries are offered back only where consent covers it.
3. **Data deletion:** all candidate personal data held by the vendor (conversations, documents, profiles, logs referencing personal data) is deleted end to end within 30 days, with a signed deletion certificate to the DPO; audit records required by law are transferred to the client, not deleted [T-laura-22, T-laura-28].
4. **No client-system writes after day 0 of exit:** no new employee-creation or rota writes; pending writes reconciled against the nightly CSV before disconnection (C-T4).
5. **Close-out report:** final metric tree readout, what worked, what did not, and the recommendation to the CPO and the board.
