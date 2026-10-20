# Concept: FirstShift

- **Phase:** 3, solution design (spec: `specs/03-solution-design.md` section 3, S4).
- **Inputs:** `design/options.md`, `design/decision-matrix.md` (approved by the human, feature log L3: "vamos con todo"), `design/problem-statement.md`, `design/metric-tree.md`, `design/constraints.md`, `discovery/insights.md`.
- **Scope of this branch:** backend and infra only. The console is described at spec level (`specs/04b-console.md`); no `web/` code is touched here.

## The concept in one sentence

> FirstShift fills a specific open shift with a person who is ready to work it, by running recruiting, pre-boarding, scheduling and the first week as one conversation, with managers deciding from WhatsApp and every client system kept as the source of truth.

## The narrative (one page)

A Saturday-close gap appears at Benidorm Playa. The manager does not open a portal; she sends one WhatsApp message, and FirstShift treats **that open shift, not the requisition**, as the unit of work. A requisition is still created in HireDesk so Talent keeps control and reporting, but matching runs against concrete ShiftGrid open shifts, because availability as a dropdown is a dead field that rejects exactly the profiles restaurants need (H2, [T-candidate-b-08 to T-candidate-b-10], [T-churned-14]).

The same hour, the candidate's phone buzzes: the agent names the restaurant, discloses that it is an AI, shows the consent notice with its version, and asks one concrete question, because the winner of a real six-chain race was the only chain that answered within the hour (H1, [T-candidate-a-10, T-candidate-a-12]). The candidate who consented answers in her language (Spanish by default, chosen explicitly, C-O4) and her availability becomes structured facts: which shifts, which restaurant, which languages (H7, [T-candidate-c-08 to T-candidate-c-10]). The agent recommends a shift fit and proposes concrete shifts; it never rejects. The candidate books an interview from the manager's real open slots, so the 38.0% no-show window stops being scheduled by phone calls from unknown numbers that about half of candidates will not answer ([T-jordi-14]).

Everything a manager owns arrives as one WhatsApp message with two or three buttons: interview slot, offer approval, first-shift slot, backup activation. No dashboard, no login, no portal (C-O1, C-O2, H5, [T-raul-26], [T-yolanda-14, T-yolanda-16]). Every button reply is logged with who, what and when, which is a governance improvement over today's unrecorded side chats ([T-laura-18, T-laura-24]).

While the decision is pending, the candidate can opt in to pre-boarding: the three chronically late documents and the LearnBite hygiene module move forward in parallel, with explicit language that completing pre-boarding never implies a hiring commitment (H3, [T-sofia-10], [T-iker-08]). After the recorded manager approval and the offer, the **promise-to-payroll tracker** owns the window everyone else forgot: which document is late, which day of the 3-to-6-day Nómina360 creation this hire sits on, when the Thursday rota lock bites, surfaced as one daily status line to the manager and People Ops, because today no system, team or report owns this transition ([T-yolanda-20], [T-sofia-18], [T-hugo-12]). "Ready for the rota" is only ever signaled on CSV-confirmed truth: the nightly Nómina360 reconciliation downgrades any API-confirmed write that the file does not show, because the July incident proved writes can fail silently under HTTP 200 (C-T3, C-T4, [T-hugo-16, T-hugo-18, T-hugo-20]), and a hire told "you start Saturday" whose alta failed is a no-show whose cause is operational, not motivational ([T-sofia-20]).

The first shift is communicated at least 24 hours ahead with logistics that answer a real newcomer's questions: address, entrance, uniform, who to ask for. The day before, one tap confirms. If confirmation has not arrived by T minus 18 hours, the named backup from the bench is activated, because the bench gives the commitment engine a backup that actually exists in 18 hours (H4, [T-churned-08, T-candidate-a-16, T-candidate-a-18]). Day 0 closes with a check-in. Then day 3 and day 10 check-ins read the promised schedule against the real rota, surface conflicts to the manager with a suggested action and an owner inside 48 hours, because week-1 quits are expectation and rota mismatch, and an unanswered channel makes it worse, not better (H6, [T-iker-14 to T-iker-16], [T-churned-22 to T-churned-24]).

The bench closes the loop: good candidates who did not fit this shift go back, with consent, to the restaurant's pool, which is Yolanda's personal-WhatsApp "maybes" list made official, visible and logged instead of competing with it (O4, [T-yolanda-14, T-yolanda-16, T-yolanda-26], [T-laura-12]). And signals flow back: the week-2 manager rating and the day-30 retention outcome are written against the screening answers, so screening criteria get revised with evidence, by humans (metric tree quality branch; C-L6).

Consciously out of the pilot: demand-triggered requisitions wait for phase 2 until the coverage signal is measured rather than overwritten (O3, [T-raul-18]); crew referrals stay out on evidence grounds (O9, no discovery evidence, matrix score 2 on evidence); voice stays v2 against explicit negative evidence (O10, [T-jordi-14]).

## The five design moves (from the spec)

1. **The unit of work is the open shift, not the requisition.** Requisition still created in HireDesk; matching against ShiftGrid open shifts (H2, [T-candidate-b-08 to T-candidate-b-10]).
2. **One continuous candidate conversation** across recruit, pre-board, first shift and first week: no repeated questions, no handoff silence (H1, [T-candidate-a-10]; H3, [T-sofia-10]).
3. **Three agent roles on one shared candidate record:** Recruit, Onboard and Pulse share state (see `design/agents.md`), mirroring the frontline HR agent product split without splitting the data.
4. **The bench closes the loop:** no candidate rejected into the void; consented silver medals, rehire-eligible ex-employees and future referrals return per restaurant (O4, [T-yolanda-14, T-yolanda-16]).
5. **Signals flow back:** day-30 retention and the week-2 rating are written against screening answers; criteria changes are proposals for humans, never automatic (C-L6; metric tree).

## Scope of the approved concept

| Element | Status in pilot | Why |
|---|---|---|
| O4 bench + O2 shift matching | Core | Highest weighted scores, 4.18 and 4.10 (`design/decision-matrix.md`) |
| O5 pre-boarding + O11 tracker + O12 CSV gate | Core, hired-to-rota engine | Attacks the largest time sink (5.1 median days; H3) |
| O6 commitment engine | Core | Direct lever on the 17.9% day-1 no-show (H4) |
| O7 manager decisions in WhatsApp | Core delivery surface | C-O1, C-O2, H5, [T-raul-26] |
| O8 early-life check-ins | Scoped component | Only lever on 28.0% day-30 attrition; conflict resolution bounded to a 48-hour owner (H6) |
| O1 fast screening | Component of first contact, not a standalone product | Matrix: front-of-funnel speed alone leaves the back window untouched |
| O3 demand-triggered requisitions | Phase 2 | Forecast input overwritten by about half of managers ([T-raul-18]) |
| O9 crew referrals | Out of pilot | No discovery evidence (matrix evidence score 2) |
| O10 voice | v2 | Evidence cuts against voice contact ([T-jordi-14]) |

## Sequence diagram: from shift gap appears to day 10 check-in

```mermaid
sequenceDiagram
    autonumber
    participant M as Manager (WhatsApp)
    participant FS as FirstShift (agents, core, workers)
    participant C as Candidate (WhatsApp)
    participant S as Client systems (HireDesk, ShiftGrid, Nómina360, LearnBite)

    Note over M,S: A gap appears: an open ShiftGrid shift will not be covered
    M->>FS: flags the gap in one WhatsApp message (buttons: open requisition, check bench)
    FS->>S: creates the requisition in HireDesk (Talent keeps control and reporting)
    FS->>S: reads open shifts and the rota lock from ShiftGrid
    FS->>FS: pulls the bench for this restaurant (O4) and ranks bench plus new applicants by shift fit
    FS->>C: first contact in minutes, in Spanish, AI disclosure, restaurant named, one concrete question
    C->>FS: consent (versioned) + language + availability as concrete shifts
    FS->>C: proposes the concrete shifts that fit (O2): a recommendation, never a decision
    C->>FS: picks a shift and books an interview from the manager's open slots
    FS->>M: interview request as one message with buttons; reminders at 24 h and 2 h
    opt candidate opts in to pre-boarding (O5)
        FS->>C: upload link (bank certificate, SS number, hygiene certificate) + LearnBite module
        C->>S: uploads documents, starts the hygiene module (no hiring commitment implied)
    end
    Note over C,M: the interview happens; answers land on the shared candidate record
    FS->>M: decision request: candidate summary and two buttons (approve, not yet)
    alt replies within 2 h
        M->>FS: Approve
    else no reply
        FS->>M: reminder at 2 h, escalation to the area HRBP at 8 h
        M->>FS: Approve (whoever approves is on the audit log)
    end
    FS->>C: sends the offer
    C->>FS: accepts
    FS->>S: validated employee-creation payload routed through People Ops into Nómina360
    FS->>M: daily tracker line (O11): documents, Nómina360 day N of 3 to 6, Thursday rota lock
    Note over FS,S: nightly reconciliation reads the Nómina360 CSV (O12): ready only on CSV-confirmed truth
    FS->>M: proposes the first-shift slot with one button
    M->>FS: confirms the slot
    FS->>C: first-shift brief 24 h ahead: address, entrance, uniform, who to ask for
    alt candidate confirms
        C->>FS: Confirmed (one tap)
    else no confirmation by T minus 18 h
        FS->>FS: activates the named backup from the bench
    end
    Note over C,M: day 0: the hire works the shift; day-0 check-in on WhatsApp
    FS->>C: day-3 and day-10 check-ins (O8): promised schedule vs real rota
    alt conflict found
        FS->>M: conflict plus suggested action, owned within 48 h
    end
    FS->>M: week-2 rating question; day-30 retention signal written back against the screening answers
```
