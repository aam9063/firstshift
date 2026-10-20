# Decision matrix

- **Phase:** 3, solution design (spec: `specs/03-solution-design.md` section 2, S2).
- **Rule:** score each option 1 to 5 on the seven spec criteria, weight impact and evidence highest, show the weighted total per option in a table sorted by total, and close with a paragraph on why the winner wins and what was consciously left out. Options are defined in `design/options.md`.
- **Gate:** per the feature document S3, this matrix is shown to the human before any concept is written. Nothing here is a commitment until that decision.

## Weights

Impact on the two target metrics and the strength of the discovery evidence carry the most weight, because the north star is a speed metric with two named levers (TTFPS and day-1 show) and the client's own candidates decide with their feet based on evidence we observed, not on our design intuition.

| Criterion | Weight | Rationale |
|---|---|---|
| Impact on TTFPS | 0.22 | Highest single weight: TTFPS is the north star (27.3 day baseline, 14 day target). |
| Impact on day-1 show rate | 0.18 | Second target metric (day-1 no-show baseline 17.9%): day 1 is where speed converts into a productive shift. |
| Evidence strength from discovery | 0.20 | Tied highest tier: options attacking observed, cited failure modes beat options attacking plausible ones. |
| Integration effort (inverse: 5 = least effort) | 0.10 | 5-day build context and Hugo's hard gates on Nómina360 make effort real but secondary to aiming well. |
| Compliance risk (inverse: 5 = least risk) | 0.12 | Laura's signature is an absolute veto (DPIA before first contact [T-laura-28]); risk weighs more than effort. |
| Manager behavior change required (inverse: 5 = least change) | 0.10 | Adoption decides the pilot: "Si Yolanda no lo usa en Benidorm, esto está muerto" [T-marta-22]. |
| Demo-ability in 5 days | 0.08 | Lowest weight: the demo matters for the pilot kickoff, not for the outcome. |

Total weight: 1.00. Combined impact weight is 0.40 and evidence is 0.20; the next highest criterion is 0.12.

## Score definitions

1 = weak or negative effect, 5 = strong effect. For inverse criteria, 5 means low effort, low compliance risk, or little manager behavior change. Every evidence-strength score names the transcripts or funnel numbers behind it; where discovery found no evidence, the score says so.

## Matrix (sorted by weighted total)

| Rank | Option | TTFPS (x0.22) | Day-1 show (x0.18) | Evidence (x0.20) | Integration inverse (x0.10) | Compliance inverse (x0.12) | Manager change inverse (x0.10) | Demo (x0.08) | Weighted total |
|---|---|---|---|---|---|---|---|---|---|
| 1 | O4 Always-warm bench | 5 | 4 | 5 | 4 | 2 | 4 | 4 | **4.18** |
| 2 | O2 Hire for shifts, not positions | 4 | 4 | 5 | 3 | 4 | 4 | 4 | **4.10** |
| 3 | O6 First-shift commitment engine | 2 | 5 | 4 | 4 | 4 | 4 | 4 | **3.74** |
| 4 | O11 Promise-to-payroll tracker | 4 | 3 | 4 | 3 | 4 | 4 | 4 | **3.72** |
| 5 | O12 CSV-truth reconciliation gate | 3 | 3 | 4 | 3 | 5 | 5 | 3 | **3.64** |
| 6 | O5 Pre-boarding in parallel | 5 | 3 | 4 | 2 | 2 | 5 | 3 | **3.62** |
| 7 | O7 Manager in the loop, in WhatsApp | 4 | 2 | 4 | 4 | 4 | 3 | 5 | **3.62** |
| 8 | O1 Faster screening bot | 3 | 2 | 5 | 3 | 3 | 4 | 5 | **3.48** |
| 9 | O9 Crew referral loop | 3 | 3 | 2 | 4 | 3 | 5 | 3 | **3.10** |
| 10 | O3 Demand-triggered requisitions | 4 | 1 | 3 | 2 | 4 | 3 | 2 | **2.80** |
| 10 | O8 Early-life check-ins | 1 | 1 | 4 | 4 | 4 | 4 | 4 | **2.80** |
| 12 | O10 Voice interview option (v2) | 2 | 1 | 2 | 2 | 2 | 4 | 2 | **2.02** |

Worked example of the arithmetic, O4: 5(0.22) + 4(0.18) + 5(0.20) + 4(0.10) + 2(0.12) + 4(0.10) + 4(0.08) = 1.10 + 0.72 + 1.00 + 0.40 + 0.24 + 0.40 + 0.32 = 4.18.

## Per-criterion justification (evidence cited)

### Evidence strength (0.20), per option

- **O4, 5.** The bench is observed, not hypothesized: about 25 "maybes" in Yolanda's personal WhatsApp [T-yolanda-14, T-yolanda-16], her last hire contacted by her before any requisition existed [T-yolanda-08], bench hires logged post-hoc which is why the Head of TA calls his own funnel reports garbage [T-yolanda-18, T-jordi-18, T-jordi-20], and the ride-along shows none of a Saturday's hiring happened in HireDesk (`discovery/ride-along-benidorm.md`).
- **O2, 5.** A candidate rejected twice for "availability" without anyone asking, whose real availability is exactly the hours restaurants suffer [T-candidate-b-08 to T-candidate-b-10, T-candidate-b-24]; a student who answered "completa" because she did not understand the dropdown [T-candidate-a-20]; a churned hire whose stated availability never reached the rota [T-churned-14]; and the format candidates say they answer [T-candidate-b-22].
- **O1, 5.** Funnel: 3.9-day median to first contact, 41.0% of 4,500 applications never contacted, only 44.2% reached screened; the candidate who won a job was the only one of six chains to reply within the hour [T-candidate-a-10, T-candidate-a-12]; "a quick no is better than a slow maybe" [T-candidate-b-18]; the pile is reviewed "if there is air" [T-jordi-14].
- **O6, 4.** Day-1 no-show 17.9% (funnel; brief §4: 18%); first shift learned the night before at 22:30 or by chance from a crew group [T-churned-08, T-candidate-a-16, T-candidate-a-18]. Strong, but the fix itself (confirmation plus backup) is untested: H4 states no comparative evidence exists.
- **O11, 4.** No system owns the hired-to-rota transition (`discovery/systems-and-data.md` key finding); Nómina360 creation takes 3 to 6 days and gates scheduling [T-yolanda-20]; "a promise" [T-sofia-18]; 11 days observed for one hire [T-yolanda-10]; rota locks Thursdays [T-hugo-12]; largest funnel time sink at 5.1 median days.
- **O12, 4.** "What is in the file is what is actually in the system" [T-hugo-18]; the July silent-failure incident under HTTP 200 [T-hugo-16, T-hugo-20]; rate limit and undocumented throttling [T-hugo-14]. The failure mode is documented by IT itself; the frequency of silent failures is not quantified.
- **O5, 4.** The three chronically late documents [T-sofia-10]; Nómina360 creation 3 to 6 days [T-yolanda-20]; a hygiene certificate once cost a 5-day start delay [T-sofia-14]; funnel 5.1 median days documents to on rota; 2 of the trainer's last 5 arrived without the module [T-iker-08].
- **O7, 4.** Managers already run hiring from personal WhatsApp [T-yolanda-14, T-yolanda-16] and reject any portal [T-raul-26]; but no baseline for approval latency exists because approvals are unrecorded side conversations (H5 states this openly), so the evidence proves the channel, not the speed gain.
- **O8, 4.** 2 of the trainer's last 5 hires quit in week 1 with "this is not what I was told" [T-iker-14 to T-iker-16]; the churned hire's unanswered swap request and night-before rota [T-churned-10, T-churned-18, T-churned-22 to T-churned-24]; 28.0% of day-1 workers gone by day 30 (funnel). Week-1 quit rate is not measured today, so the denominator is instrumented from zero.
- **O3, 3.** Coverage gap is real (7.5% of peak hours understaffed in coastal July and August, brief §4) and candidates ask for early contact ([T-candidate-c-14]: "ask me in February, not in May"), but the forecast input is corrupted by about half of managers overwriting it and the Area Director trusting calls over the screen [T-raul-18]. No evidence connects an earlier requisition to earlier or better hires.
- **O9, 2.** No direct referral evidence in discovery; the case is inferred from the informal channels that already work (the bench, WhatsApp groups [T-yolanda-16], the perfect weekend candidate saved by a WhatsApp group [T-jordi-10]).
- **O10, 2.** The only voice evidence cuts against it: about half of candidates will not answer an unknown-number call [T-jordi-14]. No candidate asked for voice.

### Impact on TTFPS (0.22), per option

- **O4 and O5, 5.** O4 removes the funnel entirely for the bench segment (the bench hire is contacted in minutes [T-yolanda-08]); O5 attacks the largest time sink directly (offer to first shift 9 to 9.5 days toward under 4, the metric-tree derivation).
- **O2, O3, O7, O11, 4.** O2 kills availability rejections and speeds screening to offer; O3 starts the pipeline weeks earlier; O7 removes unmeasured approval latency; O11 compresses the offer-to-rota window by driving one action per day of the 3-to-6-day Nómina360 wait.
- **O12, 3.** Indirect: it does not shorten the window, it prevents false "ready" states that produce day-1 failures, plus a deliberate one-day CSV confirmation lag.
- **O1, 3.** Front-door speed is real (3.9 days to minutes) but leaves the 7.5-day offer-to-rota window untouched; the front of the funnel is a smaller share of TTFPS than the back.
- **O9, 3.** Referrals convert fast but volume is unproven.
- **O6, 2.** It protects the last mile rather than shortening it; a no-show costs the full pipeline time, but confirmation does not compress the schedule.
- **O10, 2.** Marginal access effect, small candidate share.
- **O8, 1.** Starts after day 1: zero effect on TTFPS by definition.

### Impact on day-1 show rate (0.18), per option

- **O6, 5.** The direct lever on the 17.9% no-show: confirmation with logistics, cutoff, named backup (H4).
- **O4 and O2, 4.** O4's bench candidates know the restaurant and the manager; O2 matches a person to a concrete shift they explicitly accepted, which is a commitment, not an assignment.
- **O11, O12, O5, O9, 3.** O11 surfaces the "you start Saturday" promise early enough to communicate in advance; O12 prevents no-shows whose cause is a silently failed alta [T-sofia-20]; O5 means module and documents are done, removing day-1 friction; O9's social ties raise show rates plausibly but without evidence.
- **O1, O7, 2.** Indirect at best: better shortlists and faster approvals do not touch the night-before drop-off.
- **O3, O8, O10, 1.** No mechanism touches day-1 show (O8 starts after day 1; O10 is a modality; O3 changes when hiring starts, not whether the person shows).

### Integration effort inverse (0.10)

- **O7, O8, O9, 5 or 4.** O7 is the WhatsApp channel plus a message catalog (S); O8 adds a ShiftGrid rota read and two scheduled conversations (S); O9 is link generation plus notification (S).
- **O4, O6, 4.** O4 is mostly internal state plus consent flows; O6 is timers plus WhatsApp, but the backup needs the bench (O4) to be real.
- **O1, O2, O11, 3.** O1 needs HireDesk plus the channel; O2 needs ShiftGrid open-shift reads; O11 needs Nómina360 reads, ShiftGrid rota reads and a new status object.
- **O5, O3, O10, O12, 2 or 3.** O5 is the heaviest: Nómina360 employee-creation writes under C-T2, C-T3, C-T5 plus LearnBite enrollment and completion webhooks (L); O3 needs TillCloud reads, a coverage signal and an attrition model (L); O10 needs telephony and transcription (L); O12 sits at 3: a self-contained CSV job (M), but inside Hugo's hard review gate [T-hugo-22].

### Compliance risk inverse (0.12)

- **O12, 5.** Pure data integrity, improves C-T4 and C-T6, no candidate-facing surface.
- **O2, O6, O7, O8, O11, 4.** All are low-risk: recommendations with human decisions (C-L6), one-tap confirmations, logged WhatsApp decisions (which Laura explicitly frames as an improvement over personal WhatsApp [T-laura-24]), rota reads, internal status.
- **O1, O9, 3.** O1 must avoid automated rejection (GDPR article 22, C-L6) and survive the rude-screenshot test [T-marta-18, T-marta-20]; O9 shares candidate progress with a third party (the referrer) and needs its own consent.
- **O4, O5, O10, 2.** O4 is a persistent re-contactable pool: consent per channel with version (C-L1, C-L2), retention that executes (C-L4), erasure end to end (C-L5); the risk is managed, not small. O5 touches sensitive documents and a Nómina360 write path with a strict People Ops boundary (C-L9), plus the no-commitment line must hold. O10 adds voice recording consent and AI Act high-risk scrutiny (C-L7).

### Manager behavior change inverse (0.10)

- **O5, O9, O12, 5.** None of them requires a manager to change anything; two of them help People Ops instead, which is where the win is ([T-sofia-26]).
- **O1, O2, O4, O6, O8, O11, 4.** All absorb or extend what managers already do: the bench made visible instead of replaced ([T-yolanda-26] respected), concrete shift questions instead of dropdowns, confirmations and suggested actions by message.
- **O3, O7, 3.** O3 asks managers to accept requisitions they did not open, against a culture of overwritten forecasts [T-raul-18]; O7 moves decisions out of unrecorded side chats into a logged flow, which is small but real (the pattern matches existing behavior, the logging is the change).
- **O10, 4.** No manager change, but the score above assumes it ships as v2 without touching the manager flow.

### Demo-ability in 5 days (0.08)

- **O1, O7, 5.** The WhatsApp conversation and the buttons-in-WhatsApp approval are the natural demo stars: one shows speed, the other shows the manager experience with zero portal.
- **O2, O4, O6, O8, O11, 4.** Each has one clean end-to-end scenario (shift matching, bench re-engagement, confirmation cutoff, day-3 conflict, the status timeline); O11's timeline is very demoable but depends on O5-adjacent plumbing for a full story.
- **O5, O9, O12, 3.** O5's document and enrollment flow demos but the Nómina360 write path is mocked; O9 needs a two-party flow; O12's demo is the "silent write failure caught by the CSV" story, compelling for IT, less for business.
- **O3, O10, 2.** O3 needs historical data and a model to show anything honest; O10 needs a voice stack.

## Why the winner wins, and what was consciously left out

No single option wins on its own, because the scores cluster by funnel stage: the top two options (O4 at 4.18, O2 at 4.10) attack the front and middle of the funnel, the next four (O6 3.74, O11 3.72, O12 3.64, O5 3.62) attack the hired-to-rota window and day 1, and O7 (3.62) is the delivery surface that makes the rest usable for managers at all. The winning combination is therefore **O4 + O2 as the core, O5 + O11 + O12 as the hired-to-rota engine, O6 for day 1, and O7 as the manager surface, with O1 folded in as the first-contact component rather than a standalone product.** This combination wins for three reasons. First, it is the only grouping that touches every stage of the TTFPS tree with the highest-evidence lever available at each stage: bench and fast contact for the front door (41.0% never contacted, 3.9 days), shift matching for screening-to-offer (the dead availability field [T-candidate-b-08 to T-candidate-b-10]), and pre-boarding plus tracker plus CSV gate for the 7.5-day offer-to-rota window, the single largest time sink. Second, the options reinforce each other instead of adding independently: the bench gives the commitment engine its named backup (O6's main dependency), the tracker gives pre-boarding its owner-visible daily status, the CSV gate makes "ready for the rota" truthful, and O7's one-message pattern is the only interface any of it needs from a manager who rejects portals [T-raul-26]. Third, the compliance-heavy pieces (O4's consented pool, O5's no-commitment pre-boarding) are bounded by components that produce exactly the logs the DPO requires [T-laura-18, T-laura-24], turning the two riskiest options into a governance improvement over today's shadow WhatsApp process. Consciously left out: **O3 (demand-triggered requisitions) is deferred to phase 2** because its forecast input is corrupted today [T-raul-18] and the 5-day pilot must run on signal we can trust; the measured TillCloud-based coverage method from the metric tree is the precondition that makes it honest later. **O8 (early-life check-ins) scores lowest among the plausible inclusions (2.80) because it cannot move TTFPS or day-1 show at all, but it is retained as a scoped, lightweight component of the concept rather than dropped**: it is the only lever on the 28.0% day-30 attrition the combination otherwise ignores, its effort is S, and its conflict-resolution behavior will be defined narrowly so it does not become another unanswered channel. **O9 (referrals) is left out of the pilot scope** on evidence grounds (no discovery evidence, score 2 on the highest-weighted non-impact criterion) while remaining cheap to add later, since the bench it would feed is already in. **O10 (voice) is explicitly v2**: the discovery evidence argues against voice contact [T-jordi-14], and it would spend integration and compliance budget (C-L7) on the weakest case. This conclusion matches the shape the spec anticipated (options 2, 4, 5, 6, 7 and 8 with 1 as a component and 3 as phase 2), and the matrix adds O11 and O12 to that expected set because they scored above O5 and O7 individually and close the ownership and data-truth gaps that discovery named as the most expensive window in the process.
