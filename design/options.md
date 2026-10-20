# Options: ways to hit the north star

- **Phase:** 3, solution design (spec: `specs/03-solution-design.md` section 1, S1).
- **Rule:** at least 8 genuinely different options, each with a one-line idea, which hypothesis (H1 to H7, from `design/hypotheses.md`) it attacks, rough effort, main risk, and what would have to be true. The obvious options are included so the choice is visibly reasoned; the non-obvious ones are included because the evidence points there. Effort: S (days), M (one to two weeks), L (multiple weeks or a dedicated workstream). Hypotheses not attacked by any option are named at the end.
- **Scoring:** the companion document `design/decision-matrix.md` scores all twelve options and derives the winning combination.

The north star is TTFPS: median days from application to the end of the first worked shift in which the new hire completed the hygiene module (baseline about 27.3 days, target 14 or less; `design/metric-tree.md`). The single biggest time sink is the hired-to-rota window (5.1 days median, offer to first shift 9 to 9.5 days), and the single biggest conversion leak is the front door (41.0% of 4,500 applications never contacted, 3.9-day median first contact).

---

## The required ten

### O1. Faster screening bot (the literal ask)

- **One line:** a conversational screening agent on WhatsApp that answers every applicant in minutes, runs the eligibility and screening questions, and hands the talent team a ranked shortlist.
- **Attacks:** H1 (fast first contact converts the silent queue) and partially H7 (language question as a screening input).
- **Effort:** M.
- **Main risk:** it automates the front of the funnel while leaving the two real sinks untouched: the hired-to-rota window (5.1 days) and the manager's shadow process. Also the CPO's nightmare scenario, a rude bot screenshot going public [T-marta-18, T-marta-20], and Jordi's veto on black-box rejection [T-jordi-22].
- **What would have to be true:** the agent can hold a screening conversation in Spanish that candidates actually finish (candidates answer one concrete question in WhatsApp [T-candidate-b-22]); every rejection stays human [T-jordi-22, C-L6]; and the DPIA gate clears before first contact [T-laura-28].

### O2. Hire for shifts, not positions

- **One line:** the candidate is matched to concrete open shifts from ShiftGrid ("Fri and Sat 19:00 to 01:00, Benidorm Playa") instead of answering an availability dropdown, and that structured availability is carried into the rota.
- **Attacks:** H2 (concrete shift questions replace the availability dropdown).
- **Effort:** M.
- **Main risk:** depends on ShiftGrid open-shift data being current enough to match against, in a tool where managers overwrite forecasts and run the rota informally [T-raul-18]; if the shift list is stale, the conversation proposes shifts that do not exist.
- **What would have to be true:** ShiftGrid exposes readable open shifts per restaurant (documented REST API, C-T1); matching is a recommendation, never an automated rejection (C-L6); and the collected availability actually reaches the rota so it stops being a dead field (the failure documented in [T-churned-14] and [T-candidate-b-08 to T-candidate-b-10]).

### O3. Demand-triggered requisitions

- **One line:** use the TillCloud forecast plus ShiftGrid coverage plus known attrition to open hiring before the manager notices the gap, so the coastal pipeline starts weeks earlier before summer.
- **Attacks:** none of H1 to H7 directly; it attacks the coverage branch of the metric tree (7.5% of peak hours understaffed in coastal July and August) and indirectly H1 by starting the clock earlier. Candidate support exists: "if they want me for the summer, ask me in February, not in May" [T-candidate-c-14].
- **Effort:** L.
- **Main risk:** the forecast signal is unreliable today, because about half the managers overwrite the ShiftGrid labor forecast so the screen does not show red and the Area Director trusts phone calls, not the screen [T-raul-18]. Building a prediction layer on overwritten data bakes the distortion in.
- **What would have to be true:** TillCloud sales at 15-minute granularity and ShiftGrid scheduled hours can produce a trusted coverage signal with the method fixed before the pilot (the measurement note in `design/metric-tree.md`); the client accepts requisitions opened without a manager asking; and People Ops can absorb earlier, smoother volume rather than a bigger July spike.

### O4. The always-warm bench

- **One line:** formalize Yolanda's "maybes" list: silver-medal candidates, rehire-eligible ex-employees and crew referrals stay in a consented, per-restaurant talent pool that the agent re-engages the moment a gap appears.
- **Attacks:** H1 (fast contact) and H2 (these are known-shift-fit people); effectively it removes the funnel for a segment, which is the strongest TTFPS lever available.
- **Effort:** M.
- **Main risk:** compliance. A persistent re-contactable pool is exactly where the DPO's red lines live: consent per channel with timestamp and notice version (C-L1, C-L2), retention that actually executes (C-L4), end-to-end erasure (C-L5). Get the consent design wrong and the flagship feature is also the pilot's GDPR incident. Adoption risk is the inverse: if the tool competes with the personal WhatsApp bench instead of absorbing it, Yolanda uses it once and never opens it again [T-yolanda-26].
- **What would have to be true:** consent for re-engagement is captured at silver-medal time with version and channel; retention and erasure work on the pool like on any candidate; and managers see the bench as their list, made visible and logged, not as a queue owned by HQ (the insight that the bench already exists on personal WhatsApp [T-yolanda-14, T-yolanda-16] and is shadow IT the DPO cannot search [T-laura-12]).

### O5. Pre-boarding in parallel

- **One line:** with explicit opt-in, start document collection (bank certificate, social security number, food hygiene certificate) and the LearnBite hygiene module while the hiring decision is pending, so "offer accepted" and "ready for the rota" collapse into the same day, with clear language that completing pre-boarding never implies a hiring commitment.
- **Attacks:** H3 (pre-collecting documents and the hygiene module cuts offer-to-rota time).
- **Effort:** L.
- **Main risk:** it runs through Nómina360 and LearnBite, the two hardest integration surfaces: Nómina360 rate limit of 60 requests per minute, HTTP 200 with error bodies, nightly CSV as the reliable read (C-T2, C-T3, C-T4) and Hugo's veto on unlogged writes [T-hugo-22]. Second risk: the "no commitment" line blurs, which is both a candidate-trust problem and a compliance one (processing before a decision exists).
- **What would have to be true:** candidates opt in with per-channel consent (C-L1, C-L2); People Ops keeps the Nómina360 write path (C-L9, [T-sofia-04]) and accepts earlier, cleaner intake ([T-sofia-26] is the strongest internal ally quote for this); the LearnBite module is a precondition to food-handling tasks but never to hiring or an offer (C-L8, [T-iker-06]).

### O6. First-shift commitment engine

- **One line:** day-before confirmation with logistics (address, entrance, uniform, who to ask for), a day-0 check-in, and an automatic backup activation from the bench if confirmation does not arrive by a cutoff.
- **Attacks:** H4 (day-before confirmation plus a named backup cuts day-1 no-shows).
- **Effort:** M.
- **Main risk:** the backup mechanism depends on O4 existing; without a warm bench, "backup" means re-opening a requisition, which does not happen in 18 hours. Also timer hygiene: a false backup activation confuses two candidates at once.
- **What would have to be true:** the first shift is communicated at least 24 hours ahead (today it is learned the night before at 22:30 or by chance from a crew group [T-churned-08, T-candidate-a-16, T-candidate-a-18]); the confirmation is one WhatsApp question, answered in one tap; and the cutoff timer has a human-visible audit trail.

### O7. Manager in the loop, in WhatsApp

- **One line:** every decision a manager owns (interview slot, offer approval, first-shift slot, backup activation) arrives as one WhatsApp message with a short summary and two or three buttons; no dashboard, no login.
- **Attacks:** H5 (managers approve offers from a single WhatsApp message in under 2 hours).
- **Effort:** S.
- **Main risk:** no baseline exists for approval latency because today's approvals are side conversations that are never recorded (H5 states this openly); the pilot both changes the behavior and has to measure it, so attribution is soft. Secondary risk: moving decisions out of personal side chats into a logged flow is exactly the behavior change managers resist if it feels like surveillance.
- **What would have to be true:** the message pattern matches how managers already work (Yolanda runs hiring from personal WhatsApp [T-yolanda-14, T-yolanda-16]; Raúl rejects any portal [T-raul-26]; C-O1, C-O2); every button reply is logged with who, what, when (which satisfies Laura's "show me the logs" [T-laura-18] and is a compliance improvement over personal WhatsApp [T-laura-24]).

### O8. Early-life check-ins

- **One line:** day-3 and day-10 short WhatsApp conversations that read back the promised schedule against the real rota, detect conflicts and expectation mismatch, and route them to the manager with a suggested action.
- **Attacks:** H6 (check-ins catch rota and expectation mismatch, saving week-1 quits).
- **Effort:** S.
- **Main risk:** it starts after day 1, so it cannot move TTFPS or day-1 show rate at all; its value is 30-day retention (28.0% of day-1 workers gone by day 30) and week-1 quits are not measured today, so the pilot instruments from zero. If the surfaced conflicts are not resolved within 48 hours, the check-in becomes another unanswered channel, the exact failure the churned hire described [T-churned-22 to T-churned-24].
- **What would have to be true:** the rota read from ShiftGrid is reliable enough to compare against what was promised [T-hugo-12, Thursday lock]; managers act on surfaced conflicts (Iker's three conditions: module done, rota known, job understood [T-iker-22]); and the swap or fix has an owner, otherwise detection without resolution makes it worse.

### O9. Crew referral loop

- **One line:** current crew get a personal forwardable link; referred candidates are fast-tracked through screening and the referrer gets a notification when their friend starts.
- **Attacks:** H1 (speed, since referred candidates arrive pre-trusted and pre-informed) and partially H4 (social ties raise day-1 show); it is the formalized source of the bench's best inputs.
- **Effort:** S.
- **Main risk:** discovery found no direct referral evidence; the case is inferred from the informal channels that already work (WhatsApp groups, the bench [T-yolanda-16, T-jordi-10]). Second risk: notifying the referrer about the friend's progress shares candidate data with a third party and needs its own consent design.
- **What would have to be true:** referred candidates consent to the referrer notification explicitly; the fast-track is a human decision, not an automated pass (C-L6); and the crew actually forward the link, which the pilot measures from week 1.

### O10. Voice interview option (v2)

- **One line:** for candidates who prefer to talk, a short voice screening call conducted by the agent, transcribed and mapped to the same screening schema.
- **Attacks:** H1 marginally (another contact modality) and H7 (spoken language ability is easier to surface by voice).
- **Effort:** L.
- **Main risk:** the discovery evidence cuts against it: about half of candidates will not answer an unknown-number call [T-jordi-14], so voice-first contact re-creates the current failure mode. Voice recording adds consent and AI Act high-risk scrutiny (C-L7) on top of the WhatsApp flow.
- **What would have to be true:** a measurable candidate segment exists that answers voice but not WhatsApp (no discovery evidence supports this today); recording consent is per-channel and versioned like C-L2; and it ships after the text flow is proven, as v2.

## Two additional options

### O11. The promise-to-payroll tracker (owning the hired-to-rota window)

- **One line:** a per-person, per-hire status object that owns the window between verbal yes and first schedulable shift: which document is late, what day the Nómina360 creation was requested, where it sits in its 3-to-6-day range, when the rota unlocks (ShiftGrid locks Thursdays), surfaced as a daily WhatsApp status line to the manager and People Ops.
- **Attacks:** H3 (the offer-to-first-shift window) from the ownership side: today no system, team or report owns this transition (`discovery/systems-and-data.md` key finding; Sofía calls the person "a promise" [T-sofia-18]), and Yolanda's last hire took 11 days [T-yolanda-10].
- **Effort:** M.
- **Main risk:** visibility is not velocity: a tracker that shows the Nómina360 creation sitting at day 5 does not shorten it; without O5 (pre-collection) feeding it, it risks becoming a shared dashboard for a problem nobody can act on. Second risk: people-ops-sensitive data surfaced on managers' phones needs care.
- **What would have to be true:** the status line drives one action per state (chase the missing document, nudge the Nómina360 queue, warn about the Thursday lock), not just display; People Ops accepts the daily shared status ([T-sofia-26]: knowing what is missing the same day it is missing is her stated win); and the tracker reads Nómina360 state through the nightly CSV (C-T4), not through optimistic API confirmations.

### O12. The CSV-truth reconciliation gate

- **One line:** a nightly reconciliation job that reads the Nómina360 CSV export and downgrades any employee-creation write that is API-"confirmed" but absent from the file, so "ready for the rota" is only ever signaled on CSV-confirmed truth, with the mismatch alerting IT and People Ops.
- **Attacks:** H3's failure modes: a hire told "you start Saturday" whose alta silently failed will not show up, or worse, works unregistered, which Sofía names as a hard line ([T-sofia-20]: no unregistered people working shifts) and which is what "no-show" looks like when the cause is operational, not motivational.
- **Effort:** M.
- **Main risk:** by design it adds up to a one-day confirmation lag; if "ready for the rota" waits for the nightly CSV, scheduling near the Thursday lock gets tight. It also lives entirely inside Hugo's domain, so the design review is a hard gate, not a formality [T-hugo-22].
- **What would have to be true:** the CSV export is stable and parseable (Hugo: "what is in the file is what is actually in the system" [T-hugo-18]; the July incident shows writes can fail silently under HTTP 200 [T-hugo-16, T-hugo-20], which is exactly what C-T3 and C-T4 test); the one-day lag is modeled into the commitment engine's cutoffs; and every mismatch has a compensating action in the runbook (C-T7).

---

## Coverage note

- Every hypothesis H1 to H7 is attacked by at least one option: H1 (O1, O4, O7, O9), H2 (O2, O4), H3 (O5, O11, O12), H4 (O6, O9), H5 (O7), H6 (O8), H7 (O1 within the screening flow; language collection is a component, not a standalone option).
- The metric-tree branches map as: front-door speed and contact (O1, O4), screening to offer (O2, O7), offer to rota (O5, O11, O12), day-1 show (O6, O4), post-hire retention (O8), coverage (O3), plus O9 and O10 as channel and source extensions.
- Twelve options are listed against a required minimum of eight. The decision matrix scores all twelve and derives the combination.
