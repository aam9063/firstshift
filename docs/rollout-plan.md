# Rollout plan: FirstShift at Lumbre Burger Group

**Audience:** Marta Ibáñez (CPO), Raúl Sempere (Area Operations Director, Costa Blanca), Jordi Puig (Head of Talent Acquisition), and the pilot's named wave owners.
**Status:** plan for the 12-restaurant Costa Blanca pilot (brief section 6), written for the human side of the change. Entry and exit criteria per wave follow `specs/06-integration-rollout.md` section 4; security gates follow `docs/security-and-compliance.md`.
**Fictional client, real constraints:** every number below traces to `specs/00-client-brief.md` (the baseline), the discovery transcripts, or an eval report; citations are inline.

---

## 1. The four waves

| Wave | Scope | Entry criteria | Exit criteria | Owner |
|---|---|---|---|---|
| 0. Shadow | 2 restaurants; agent runs, humans see suggestions, nothing is sent to candidates | Security pack signed by IT (Hugo) and the DPO (Laura); signed DPIA dated before any outbound capability (C-X1) | Suggestion quality reviewed by Talent on 50 cases | Talent Acquisition lead (Jordi's team) |
| 1. Assisted | Same 2 restaurants; agent talks to candidates, every manager decision explicit | Wave 0 exit; managers trained (10-minute onboarding delivered in-restaurant) | 2 weeks, guardrails green, manager NPS collected | Talent + Ops jointly |
| 2. Pilot | All 12 pilot restaurants | Wave 1 exit; weekly ops review in place | Day-30 go/no-go against the pilot charter (`design/pilot-charter.md`) | Raúl Sempere, with Talent |
| 3. Expand | Remaining Costa Blanca units (Raul's area is 42 restaurants [T-raul-02]), then Algarve in Portuguese | Day-90 results meet targets (`docs/pilot-sim-day90.md`) | Steering approval | CPO + Area Directors |

### 1.1 Wave detail

**Wave 0, shadow (2 restaurants).** The agent and the pipeline run for real, but every agent send is held: Talent sees the suggestion in the console and approves or discards. Nothing reaches a candidate. This is where the eval suite meets live-shaped traffic: golden conversations and red-team personas run against the real inbound flow shape.

**Wave 1, assisted (same 2 restaurants).** The agent sends; the guardrails from `design/guardrails.md` are the contract: disclosure in the first message (G1), consent gate per channel (G2), no automated rejection or offer (INV-1, INV-2), escalation to a human on distress (G5). Every manager decision is an explicit WhatsApp quick reply. Exit needs two weeks with guardrails green in the eval reports and a collected manager NPS.

**Wave 2, pilot (12 restaurants).** All Alicante-province pilot restaurants from the signed scope, with the 3 comparable control restaurants untouched (brief section 6). The weekly ops review starts here: DLQ health, NPS, time-to-first-shift against the 3.8-day baseline, manager hours against the ~6 h/week baseline (brief section 4). The day-30 readout goes to the steering group, presented by Raul (section 2.1).

**Wave 3, expand.** First the rest of the Costa Blanca (the units that break every July [T-raul-04]), then the Algarve units where the candidate conversation must work in Portuguese (brief section 1: 70 units in Portugal; C-O4 requires Portuguese support, already designed into the notice and message catalog). The March hiring surge for summer 2027 (brief section 5, [T-marta-26]) is the hard deadline this wave must beat.

---

## 2. Change management, concretely

Software does not change how Lumbre hires; these six moves do. Each is tied to the stakeholder evidence that motivated it.

### 2.1 Raúl presents the day-30 numbers

At the day-30 go/no-go, the results of the 12 pilot restaurants are presented by Raúl Sempere to the other area directors, not by the vendor. Why: the coast is his ("La costa es suyo", [T-marta-24]), and he said it himself: if August gaps close in days instead of weeks, "yo soy el primero defendiéndolo en la reunión de dirección" [T-raul-24]. A peer operations director presenting numbers is adoption; a vendor presenting numbers is a PowerPoint. The readout format is the day-90 structure (`docs/pilot-sim-day90.md`): results vs charter, cost per hire vs the 420 EUR baseline, what changed.

### 2.2 Managers: 10-minute in-restaurant onboarding

Managers get a single one-page quickstart, delivered in the restaurant in 10 minutes by the area team, mostly screenshots of the WhatsApp messages they will receive (`docs/training/manager-quickstart.md`). No portal, no password, no dashboard: "Si me dices que la gerente tendra que entrar cada manana en un portal nuevo, ya me has perdido" [T-raul-26]; a manager stops using any tool that costs her time [T-yolanda-26]. The quickstart covers exactly the four things a manager does: reply to a candidate suggestion, approve or reject an offer (one tap), confirm a first shift, and answer a payroll-chase nudge.

### 2.3 Yolanda's maybes imported into the bench, with consent

Yolanda Ferrer hires from a personal WhatsApp list of about 25 "maybes": ex-employees, crew friends, walk-ins [T-yolanda-14, T-yolanda-16], and she logs those hires late or never [T-yolanda-18]. If the tool "puts a stranger between me and the twenty-five names I already trust", she will never open it [T-yolanda-26]. So wave 1 starts by importing her maybes list into the per-restaurant bench: each person receives a versioned, explicit re-engagement consent question per channel, captured with timestamp and notice version (`BenchEntry` + `Consent`, ADR-0005). No consent, no entry. The tool begins by doing what she already does, in a place the DPO can finally see [T-laura-24].

### 2.4 Talent team: the new weekly routine

Jordi's team of 14 today screens about one in three applications when there is air, on criteria that structurally drop the best weekend candidates (no CV) [T-jordi-08, T-jordi-12], and the final rejection is always signed by a person [T-jordi-22]. Under FirstShift they move from screening CVs to supervising conversations. The new weekly routine (starts in wave 1, mandatory from wave 2):

| Day | Routine | Output |
|---|---|---|
| Monday | Review the escalations and takeover list from the weekend; close open human_needed items | Every escalation resolved or owner-named |
| Tuesday | Decision audit sample: trace 10 offers and 10 rejections to a named human and the facts seen (C-L6) | Audit note appended to the weekly review |
| Wednesday | Review agent-vs-human suggestion quality on the week's cases; tune nothing alone | Proposals, never auto-changes (G7) |
| Thursday | Criteria-change proposals reviewed and approved or declined with evidence | Approved proposal events with named approver |
| Friday | Funnel read vs baseline (3.8-day first contact, 41% never contacted, 38% no-show) and feed the weekly ops review | One page for the ops review |

### 2.5 Payroll receives complete packs with a "ready" flag

Sofía Marques's team chases the same three late documents per hire (bank certificate, social security number, hygiene certificate) with three or four reminder emails each [T-sofia-10, T-sofia-16], and every incomplete pack is "a person who is not an employee, they are a promise" [T-sofia-18]. From wave 2, Payroll receives complete, validated document packs with a single "ready" flag: the flag is only signaled after the documents are checked and the write is confirmed by the nightly Nómina360 CSV, never by the API response alone (C-T4, INV-3, INV-9). No first shift is scheduled without it or an explicit recorded People Ops exception (INV-3), which kills the retroactive-regularisation failure [T-sofia-20, T-sofia-22].

### 2.6 A WhatsApp FEEDBACK keyword for managers

Managers text `FEEDBACK ...` to the FirstShift WhatsApp number at any moment. The message lands, with restaurant and timestamp, in the weekly ops review backlog. Nothing else changes for the manager: it is the same WhatsApp thread where they already make decisions (C-O1, ADR-0004). Why it exists: managers' operational knowledge lives in phone calls, not systems [T-raul-18, T-raul-20]; the keyword converts that knowledge into review input without asking anyone to open a tool. It feeds the same weekly review where the Talent routine (2.4) and the wave-2 exit evidence come together. **Status: designed, not yet implemented**; the keyword handler joins the inbound keyword dispatcher in `app/api/webhooks_whatsapp.py` before wave 2.

---

## 3. Gates and evidence per wave
| Gate | Evidence | Where recorded |
|---|---|---|
| Before wave 0 | Signed security pack (Hugo, Laura); signed DPIA dated before the first outbound send (C-X1) | `docs/security-and-compliance.md` sign-off block |
| Wave 0 exit | 50 reviewed suggestions with Talent verdicts | Weekly review notes + eval report |
| Wave 1 exit | 2 weeks guardrails green (eval reports with 0 failing deterministic checks), manager NPS collected | `evals/reports/`, NPS sheet |
| Wave 2 exit | Day-30 go/no-go vs `design/pilot-charter.md`, presented by Raul | Day-30 readout |
| Wave 3 entry | Day-90 results vs targets, cost per hire vs 420 EUR baseline with formula, simulation caveat visible | `docs/pilot-sim-day90.md` |

Numbers traceability: 12 pilot and 3 control restaurants, EU hosting and "no new app" constraints, and all baselines (3.8 days, 41%, 38%, 18% day-1 no-show, ~6 h/week manager time, 420 EUR cost per hire) come from `specs/00-client-brief.md` sections 4 and 6. Stakeholder citations refer to `discovery/transcripts/`.
