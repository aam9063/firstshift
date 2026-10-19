# Pain points: crew hiring, ranked

- **Scope:** the 12 pilot restaurants, annualized.
- **Ranking rule (spec 7):** frequency x impact on labor coverage x cost. Frequency and cost come from the funnel output (`uv run python -m mocks.funnel`) scaled to the pilot scope; every rate is either script output, the brief baseline (`specs/00-client-brief.md` section 4), or a transcript citation. No rate is invented.
- **Evidence key:** `[T-name-NN]` = line in `discovery/transcripts/name.md`; "funnel" = the seeded script output; "ride-along" = `discovery/ride-along-benidorm.md`.

## Shared derivations (shown once, reused below)

The dataset covers 15 restaurants over 6 months. Scaling to 12 pilot restaurants over 12 months: factor = (12 / 15) x (12 / 6) = 1.6.

| Quantity | Funnel (15 rest, 6 mo) | Pilots (12 rest, 12 mo) |
|---|---|---|
| Applications | 4500 | 7,200 |
| Never contacted | 1845 | 2,952 |
| Interviews scheduled | 1394 | 2,230 |
| Interview no-shows | 530 | 848 |
| On rota | 396 | 634 |
| Day-1 no-shows | 71 | 114 |
| Day-1 worked | 325 | 520 |
| Gone by day 30 | 91 | 146 |

Conversion rates used, straight from the funnel: applied to day-1 worked = 325 / 4500 = 7.2%; attended to day-1 worked = 325 / 864 = 37.6%; day-1 to day-30 retention = 72.0% (loss 28.0%).

**Cost anchor:** cost per hire 420 EUR (ads + HR time + manager time, `specs/00-client-brief.md` section 4). **Assumption used in every formula, stated once:** a lost hire-equivalent must be re-recruited, so it costs the group one more 420 EUR cost per hire. The 420 EUR is the group's own internal estimate; no other EUR rate exists in the evidence, so none is used.

---

## PP1. Interview no-shows: 38% of scheduled interviews never happen

- **Frequency:** 848 no-shows per year in the pilot scope (funnel: 62.0% scheduled to attended).
- **Impact on labor coverage:** high. Every no-show is a shift that stays open during the exact window when candidates are shopping multiple chains; the manager restarts the search (ride-along, 20:15 row: a maybe declines, the gap reopens). The brief anchors what this produces: 7.5% of peak hours understaffed in July and August in coastal units.
- **Evidence:** funnel (interview_scheduled 1394, interview_attended 864); [T-jordi-14] (phone tag on unknown numbers, half do not answer); [T-candidate-c-12] (a week waiting for a manager call, she moved on); [T-candidate-b-18] ("a quick no is better than a slow maybe").
- **Cost formula:** 848 no-shows/yr x 37.6% (attended to day-1 conversion, the share that would have become hires) = 319 lost hire-equivalents x 420 EUR = **133,980 EUR/yr**.
- **Rank rationale:** largest quantified cost and top-tier frequency.

## PP2. The silent queue: 41% of applicants are never contacted

- **Frequency:** 2,952 candidates per year in the pilot scope (funnel: applied 4500, contacted 2655, median 3.9 days to first contact).
- **Impact on labor coverage:** high. The queue is per vacancy and is only looked at when someone has time, about 1 application in 3 ([T-jordi-06]), and the people it drops are the fast, available profiles: students and first-jobbers who apply to six chains in one evening and take the first answer ([T-candidate-a-08 to T-candidate-a-12]).
- **Evidence:** funnel; [T-jordi-04, T-jordi-14] (he knows the leak by complaints, not reports); [T-candidate-a-12] (the only chain that answered won); brief section 4 (41% never contacted, 3.8 days median).
- **Cost formula:** 2,952 never-contacted/yr x 7.2% (applied to day-1 conversion, the share that would have converted at the funnel's own rate) = 213 lost hire-equivalents x 420 EUR = **89,460 EUR/yr**. This is conservative: [T-jordi-08] says the pile's casualties include the best weekend-shift profiles, so the real conversion of the lost group is likely higher than the funnel average.
- **Rank rationale:** the largest absolute candidate loss in the funnel (funnel-baseline.md, -1,845) and the second largest cost.

## PP3. New hires quit within weeks: expectation and rota mismatch, not the job

- **Frequency:** 146 of 520 day-1 workers per year are gone by day 30 in the pilot scope (funnel: 325 day-1 worked, 234 day-30 active, 28.0% loss; brief: 52% attrition at 90 days).
- **Impact on labor coverage:** high, because the quit lands after the restaurant already counted the person and stopped recruiting for the slot.
- **Evidence:** [T-iker-13 to T-iker-16] (2 of his last 5 quit in week 1, both saying the same words: this is not what I was told); [T-churned-08, T-churned-18, T-churned-24] (first rota the night before, a shift against her declared evening-only availability, a swap request that went unanswered, "the work I liked"); [T-churned-26] (exit logged as "personal reasons", the real cause operational); [T-candidate-a-16] (first shift learned by chance from a crew WhatsApp group the night before).
- **Cost formula:** 146 early quits/yr x 420 EUR = **61,320 EUR/yr** for the wasted first hire alone; if each is backfilled at the group's own cost per hire, the total doubles to about 122,640 EUR/yr.
- **Rank rationale:** third by direct cost, and the loss lands at the worst moment for summer coverage.

## PP4. The hired-to-rota gap: signed but unschedulable, and nobody owns it

- **Frequency:** 114 day-1 no-shows per year in the pilot scope (funnel: on_rota 396, day1_worked 325, 17.9% no-show), on top of 634 hires per year passing through the window.
- **Impact on labor coverage:** the highest per event. The candidate said yes, the manager is short today, and the person cannot be scheduled until Nómina360 creates them, 3 to 6 days ([T-yolanda-20]), with the rota locking only on Thursdays ([T-hugo-12]). This window is the largest time sink in the funnel: 5.1 median days, the biggest stage median of all (`discovery/funnel-baseline.md`). Yolanda lost a signed, good candidate to a competitor three streets away after four days of it ([T-yolanda-22]); her last hire waited 11 days ([T-yolanda-10]). It is a direct feed into the 7.5% of peak hours already understaffed in coastal July and August (brief section 4).
- **Evidence:** `discovery/systems-and-data.md` key finding (no system owns hired to on rota); [T-sofia-18] (payroll: "they are a promise"; managers: "they want the people on Saturday"); [T-sofia-10, T-sofia-14] (the same three documents late every time; a hygiene certificate alone cost a 5-day start delay); ride-along (copy-paste events 2 and 4: the manager is the integration between Nómina360 and ShiftGrid).
- **Cost formula:** 114 day-1 no-shows/yr x 420 EUR = **47,880 EUR/yr** in wasted recruitment, plus 634 hires/yr x 5.1 median days = 3,233 person-days per year of signed-but-unschedulable waiting, plus its share of the 7.5% understaffed peak hours. The direct EUR figure understates this pain point: it is the mechanism behind day-1 no-shows, competitor losses and summer understaffing, and it is the bottleneck `discovery/insights.md` leads with.
- **Rank rationale:** fourth by direct cost only. By per-event impact on peak coverage it is first, which is why the insights readout opens with it.

## PP5. Manager time drain: hiring runs on the manager's personal phone, during service

- **Frequency:** continuous. ~6 hours per week per restaurant on hiring (brief section 4) = 6 x 52 x 12 = **3,744 manager-hours per year** across the pilots. In one observed peak Saturday: 13 hiring-related interruptions, about 105 minutes of hiring work, 4 copy-paste events between systems, none of it in HireDesk (ride-along, Counts section).
- **Impact on labor coverage:** medium but structural: the person responsible for service throughput is also the unpaid integration layer between HireDesk, email, Nómina360 and ShiftGrid, and hiring work peaks exactly when service peaks ([T-yolanda-24]: drive-thru over five minutes while she scanned documents in the back office).
- **Evidence:** ride-along; [T-yolanda-06, T-yolanda-12, T-yolanda-16]; [T-jordi-18, T-jordi-20] (post-hoc logging to make the numbers fit, which is also why HireDesk reports are unreliable).
- **Cost formula:** hours only. 6 h/week x 52 weeks x 12 restaurants = 3,744 h/yr. No EUR rate for manager time exists in the brief or the transcripts, so none is applied; at any plausible loaded hourly rate this is a six-figure line item, but the honest number from the evidence is the hours.
- **Rank rationale:** ranked by frequency and by the operational risk it creates (shadow data, [T-hugo-26]; GDPR blind spot, [T-laura-12]) rather than by EUR.

## PP6. Screening criteria filter out the best-converting profile

- **Frequency:** applies to every application: about 1 in 3 is reviewed at all ([T-jordi-06]), and "complete CV first" ([T-jordi-06], [T-jordi-08]) structurally deprioritizes students and first-job applicants, the exact profile that converts best for weekend shifts. Only 1,991 of 4,500 applications (44.2%) reached screened in the funnel.
- **Impact on labor coverage:** high, but its losses are the same candidates counted in PP2 and PP1: thin-CV applicants sink in the uncontacted queue and the no-show window. Costing it separately would double-count.
- **Evidence:** [T-jordi-08] ("se caen de la pila sin que nadie los haya leído", they fall out of the pile without anyone having read them); [T-jordi-10] (the 19-year-old saved by luck, via a WhatsApp group, not the tool); [T-candidate-a-06, T-candidate-a-20] (first-job forms are thin and the availability dropdown gets answered untruthfully).
- **Cost formula:** **not separately costed, by design.** Its effect is embedded in the PP2 and PP1 formulas. The design fix is different from those two (change what screening ranks by, keep the human decision, [T-jordi-22]), which is why it is listed as its own pain point.
- **Rank rationale:** last by standalone cost, first by how cheap the fix is relative to the coverage it unlocks.

---

## Summary table

| Rank | Pain point | Frequency (pilots, /yr) | Coverage impact | Est. annual cost |
|---|---|---|---|---|
| 1 | PP1 Interview no-shows (38%) | 848 no-shows | High | 133,980 EUR |
| 2 | PP2 Silent queue, never contacted (41%) | 2,952 candidates | High | 89,460 EUR |
| 3 | PP3 Early attrition (28% gone by day 30) | 146 quits | High | 61,320 EUR (122,640 with backfill) |
| 4 | PP4 Hired-to-rota gap (5.1 day median, no owner) | 114 day-1 no-shows, 634 hires through the window | Highest per event | 47,880 EUR direct + 3,233 person-days + share of 7.5% understaffed peak hours |
| 5 | PP5 Manager time drain | 3,744 h/yr | Medium, structural | hours only, no EUR rate in evidence |
| 6 | PP6 Screening bias vs best-converting profile | every application | High (embedded in 1 and 2) | not separately costed, would double-count |

The ranking is by quantified annual cost with coverage impact noted. PP4 ranks fourth by that measure and first by per-event damage, and it is the pain point no single team can fix today, because no system owns the window (`discovery/systems-and-data.md`).
