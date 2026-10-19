# Problem statement: crew hiring, Lumbre Burger Group

- **Phase:** 2, problem framing (spec: `specs/02-problem-framing.md`).
- **Evidence rules:** every number traces to `specs/00-client-brief.md` section 4 (brief §4), `discovery/funnel-baseline.md` (funnel), or a transcript line ID `[T-name-NN]`. Nothing else is cited as fact.

## 1. The reframe in three layers

The client asked for "AI to screen candidates faster" (spec section 1).

| Layer | Statement |
|---|---|
| What they asked | Faster screening of crew applicants |
| What they need | Enough trained people on the rota at peak hours in coastal restaurants |
| What blocks it | The time and drop-off between "candidate applies" and "candidate works a first prepared shift", spread across systems nobody connects: 3.9 median days to first contact with 41.0% of applicants never contacted (funnel), a 38.0% interview no-show rate (funnel; brief §4), and a hired-to-rota window of 5.1 median days, the largest stage gap in the funnel, that no system or team owns (`discovery/systems-and-data.md` key finding; [T-yolanda-20], [T-sofia-18], [T-hugo-12]). Screening itself is not the bottleneck: the funnel already moves 75.0% of contacted applicants to screened, and the Head of TA reviews only about 1 in 3 applications "when there is air" [T-jordi-06]. |

The evidence behind the third layer, in one line each:

1. **Front door:** 1,845 of 4,500 applications never contacted, the largest absolute loss in the funnel by more than double the next stage (funnel). Candidates apply to six chains in one evening and take the first that answers [T-candidate-a-06 to T-candidate-a-12].
2. **Middle:** 5.0 median days between interview scheduling and attendance, the window where the 38.0% no-show happens (funnel), driven by slow scheduling and phone calls from unknown numbers that about half of candidates will not answer [T-jordi-14].
3. **Back door:** the hired-to-rota window, 5.1 median days from documents complete to on rota (funnel), inside the 9-day median from verbal offer to first worked shift (brief §4). Nómina360 employee creation takes 3 to 6 days and gates scheduling [T-yolanda-20], the rota locks only on Thursdays [T-hugo-12], and the same three documents arrive late every time [T-sofia-10]. A signed candidate was lost to a competitor three streets away after four days of this wait [T-yolanda-22].
4. **After day 1:** 28.0% of day-1 workers are gone by day 30 (funnel), and the causes are operational: first rota learned the night before, shifts against declared availability, unanswered swap requests [T-iker-14 to T-iker-16; T-churned-08, T-churned-18, T-churned-24].

## 2. Problem statement

> **For** crew candidates and restaurant managers **at** the 12 company-operated Lumbre Burger restaurants in Alicante province (Costa Blanca), **when** a candidate applies for a crew job in a market where she applies to six chains in one evening and takes the first that answers [T-candidate-a-06 to T-candidate-a-12], **the current process** takes a median of 3.8 days to first contact and never contacts 41% of applicants at all (brief §4; funnel: 3.9 days, 41.0%), loses 38% of scheduled interviews to no-shows and 18% of signed hires to day-1 no-shows (brief §4; funnel: 38.0%, 17.9%), and leaves the hired-to-rota window, 5.1 median days and the largest gap in the funnel, with no owner between payroll ("they are a promise" [T-sofia-18]) and operations ("I need people on Saturday" [T-raul-02]), **which causes** 7.5% of peak hours to run understaffed in coastal July and August and 11 drive-thru lane closures last summer (brief §4 and section 5), 52% of new hires gone within 90 days (brief §4), roughly 6 hours per restaurant per week of manager time spent on hiring during service (brief §4; observed: 105 minutes and 13 interruptions on one Saturday, `discovery/ride-along-benidorm.md`), and only 325 of 4,500 applications, 7.2%, reaching a first worked shift after a median of roughly 27.3 days (funnel). **We will know it is solved when** the median time from application to a first productive shift (food hygiene module completed before starting) drops from about 27 days to 14 days or less in the pilot restaurants, with the contacted rate at 95% or more, day-1 no-shows under 8%, 30-day retention at 80% or more, and the guardrails (candidate satisfaction, fairness parity, escalation SLA, zero GDPR incidents) not worse than today.

Every number traced:

| Number in the statement | Source |
|---|---|
| 3.8 days to first contact, 41% never contacted | brief §4; funnel (3.9 days, 41.0%) |
| 38% interview no-shows, 18% day-1 no-shows | brief §4; funnel (38.0%, 17.9%) |
| 5.1 median days hired-to-rota, largest gap | funnel |
| 9 days offer to first worked shift | brief §4 (funnel sum of stage medians: 9.5) |
| 7.5% peak hours understaffed, 11 lane closures | brief §4; brief section 5 |
| 52% attrition at 90 days | brief §4 |
| ~6 h/week manager time on hiring | brief §4; ride-along counts |
| 325 of 4,500 = 7.2%, ~27.3 days | funnel |
| 14-day target | derived in `design/metric-tree.md` from funnel stage medians |

## 3. Jobs to be done

One per actor. Format: "When ..., I want to ..., so I can ...".

| Actor | Job to be done | Evidence |
|---|---|---|
| Candidate | When I apply to several chains in one evening, I want a fast, concrete answer that names the restaurant and asks about real shifts, so I can take the first good job before it disappears. | [T-candidate-a-08 to T-candidate-a-12]; [T-candidate-b-18, T-candidate-b-22]; [T-candidate-c-12] (a week of waiting lost her to the beach bar) |
| Restaurant manager | When I am short for Saturday's close, I want a hire who said yes to reach the rota in days, through WhatsApp, without a new portal, so I can cover service instead of doing paperwork during it. | [T-yolanda-10, T-yolanda-20, T-yolanda-24, T-yolanda-26]; [T-raul-26] |
| Talent team | When applications pile up faster than my team can read them, I want the pile ranked by shift fit with every rejection signed by a person, so nobody good sinks unread and I keep control of who is hired. | [T-jordi-06, T-jordi-08, T-jordi-22, T-jordi-24] |
| Payroll (People Ops) | When a hire says yes, I want complete, checked documents arriving in one place the day they are missing something, so I can register and create the employee before anyone works without an alta. | [T-sofia-04, T-sofia-10, T-sofia-18, T-sofia-26, T-sofia-30] |
| Crew trainer | When a new hire lands, I want advance notice, the hygiene module done before day 1, and a rota both of us know, so I can make them useful in a week instead of inventing cleaning tasks. | [T-iker-06 to T-iker-08, T-iker-20, T-iker-22] |
| Area ops | When the season peaks, I want understaffed peak hours covered in days, not weeks, so the drive-thru lane stays open and sales do not walk to the competition. | [T-raul-02, T-raul-08, T-raul-20, T-raul-24] |

**Conflicts, named:**

- **Talent team vs restaurant manager.** Talent wants control of who is hired and a trustworthy funnel [T-jordi-22]; the manager wants to hire whoever she trusts this week, from a personal "maybes" list, before any requisition exists, and logs it afterwards only if asked [T-yolanda-14, T-yolanda-16, T-yolanda-18]. Any design that competes with the bench loses; it must adopt it with consent and logging.
- **Payroll vs restaurant manager and area ops.** Payroll's definition of ready is registration, alta and complete documents ("a promise" until then [T-sofia-18]); managers want the person on Saturday and sometimes rota them before registration, creating unregistered work that payroll must regularise [T-sofia-20, T-sofia-22].
- **Candidate vs talent team.** The candidate wants a quick no rather than a slow maybe [T-candidate-b-18]; the team cannot even contact 41% of applicants, so the conflict is capacity, not intent: the fix is speed at the front door, not more recruiters.
- **Area ops vs compliance and documentation.** Raúl needs speed and will veto any new portal [T-raul-26]; the labour inspection already flagged inconsistent documentation timelines in two units (brief section 5), so the design cannot buy speed by cutting the compliance record. A governed channel must be both faster and more auditable than personal WhatsApp [T-laura-24].
