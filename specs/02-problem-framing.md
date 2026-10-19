# 02 · Problem framing: decide what we are actually solving

**Goal:** turn discovery into a sharp problem definition, a measurable target and explicit constraints, so that Phase 3 designs for the real bottleneck and the pilot has a success criterion everyone signed before any code exists.

**Outputs (in `design/`):** `problem-statement.md`, `metric-tree.md`, `hypotheses.md`, `constraints.md`, `non-goals.md`, `assumptions.md`, and a one-page `pilot-charter.md`.

---

## 1. Reframe the request

The client asked for "AI to screen candidates faster". Write the reframe in three layers:

| Layer | Statement |
|---|---|
| What they asked | Faster screening of crew applicants |
| What they need | Enough trained people on the rota at peak hours in coastal restaurants |
| What blocks it | Write it from discovery evidence (expected: the time and drop-off between "candidate applies" and "candidate works a full first shift prepared", spread across systems nobody connects) |

Then write the problem statement in this exact form:

> **For** [who] **at** [where], **when** [situation], **the current process** [what fails, with numbers], **which causes** [business consequence, with numbers]. **We will know it is solved when** [measurable outcome].

## 2. Jobs to be done

Write one JTBD per actor: candidate, restaurant manager, talent team, payroll, crew trainer, area ops. Format: "When ..., I want to ..., so I can ...". Note which ones conflict (for example, Talent wants control of who is hired, the manager wants to hire whoever she trusts this week).

## 3. Metric tree

North star: **Time to first productive shift (TTFPS)**: median days from application to the end of the first worked shift in which the new hire completed the food hygiene module before starting.

Build the tree below it, each with baseline (from `00-client-brief.md` or `discovery/funnel-baseline.md`) and pilot target:

- Speed: time to first contact, time to interview, time from offer to on-rota.
- Conversion: contacted rate, interview show rate, offer acceptance, day-1 show rate.
- Quality: 30-day and 90-day retention of pilot hires, manager rating of the hire after week 2 (1 to 5, one WhatsApp question).
- Effort: manager minutes per hire, talent team touches per hire.
- Coverage (business outcome): % of peak hours understaffed in pilot restaurants.

**Guardrail metrics** (must not get worse): candidate satisfaction (one-question CSAT at end of conversation), fairness parity across age band, nationality and language (see Phase 5), escalation rate to humans handled within SLA, zero GDPR incidents.

Add a short section on **attribution**: how the pilot (12 units) vs control (3 units) comparison will separate the effect of FirstShift from seasonality, and its limits with this sample size. Be honest that 3 control units is weak and propose a stronger option (for example, staggered rollout).

## 4. Hypotheses

List 5 to 7 falsifiable hypotheses, each with the metric that tests it and the threshold that would make us drop it. Expected shape:

- H1: Contacting applicants on WhatsApp within 5 minutes raises interview show rate from 62% to 80% or more.
- H2: Matching candidates to concrete open shifts in ShiftGrid (instead of free-text availability) raises offer acceptance and 30-day retention.
- H3: Starting document collection and the food hygiene module **before** the interview (for candidates who opt in) cuts offer-to-rota time from 9 to 3 days or less.
- H4: A day-before confirmation plus a backup candidate cuts day-1 no-shows from 18% to under 8%.
- H5: Managers will approve offers from WhatsApp in under 2 hours median if the request is a single message with a summary and two buttons.
- H6: A day-3 and day-10 check-in catches rota conflicts and expectation mismatch early enough to save a share of week-1 quits.

Adjust numbers to what discovery found.

## 5. Constraints

Group them and write each as a testable rule the design must satisfy:

**Legal and compliance (EU and Spain)**
- GDPR: lawful basis and transparent notice before processing; data minimization; retention limits for rejected candidates; right of access and erasure; records of processing.
- No decision based solely on automated processing that significantly affects the candidate (GDPR article 22): every reject and every offer has a human decision-maker on record.
- EU AI Act: AI systems used for recruitment and selection are listed as high-risk in Annex III. Design for human oversight, logging, transparency to candidates that they talk to an AI, and documented data governance. Note in `constraints.md` that the application dates of high-risk obligations have been under revision and must be checked at deployment time.
- Food hygiene: Spanish law no longer requires a "carnet de manipulador", but the employer must ensure and be able to show food hygiene training. Treat the LearnBite module as a precondition to food-handling tasks, not to hiring.
- Contracts and Social Security registration stay with People Ops in Nómina360. FirstShift prepares and validates data; humans sign and register.

**Operational**
- No new app or dashboard for managers or crew (brief section 6). Managers act via WhatsApp messages with quick-reply buttons.
- Must work for franchisees later without code changes (multi-tenant by brand and by restaurant).
- Spanish first; Portuguese and English supported.

**Technical**
- Only documented APIs. Respect Nómina360's rate limit and quirks.
- EU data residency for data at rest.
- Every write to a client system is idempotent, logged and reversible or compensable.

## 6. Non-goals

Write at least 6 explicit non-goals with a one-line reason each. Expected: automated rejection, salary negotiation, replacing the ATS, building a scheduling engine, performance management, franchisee rollout during the pilot, voice interviews in v1 (note as a v2 candidate).

## 7. Pilot charter

One page: problem statement, north star with baseline and target, guardrails, scope (12 + 3 restaurants, 90 days), roles (client and vendor), decision cadence (weekly 30-min ops review, bi-weekly steering), go/no-go criteria at day 30 and day 90, and the exit plan if the pilot fails (data deletion, handover of conversations to HR).

## Exit criteria

- [ ] Problem statement in the exact form above, every number traced.
- [ ] Metric tree with baseline, target and data source per metric.
- [ ] At least 5 hypotheses with kill thresholds.
- [ ] Constraints written as testable rules and referenced later by Phase 3.
- [ ] Pilot charter fits on one page.
