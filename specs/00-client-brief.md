# 00 · Client brief: Lumbre Burger Group (fictional)

> Everything in this document is fictional. Numbers are plausible assumptions for a mid-size Iberian QSR operator and are the **baseline** for the simulation. Agents must not contradict them; if a phase needs a number that is not here, it must be labeled as an assumption and added to `design/assumptions.md`.

## 1. Company snapshot

| Item | Value |
|---|---|
| Name | Lumbre Burger Group (LBG) |
| Brands | Lumbre Burger (flame-grilled burgers, flagship) and Pollo Lumbre (fried chicken, 40 units) |
| Footprint | 310 restaurants: 240 in Spain, 70 in Portugal |
| Operating model | 82% company-operated, 18% franchised (franchisees run their own HR but may opt into central tools) |
| Formats | High street, shopping mall food court, drive-thru (45% of units), motorway service areas |
| Crew headcount | ~9,800 (peaks at ~12,200 in July and August) |
| Hires per year | ~11,000 crew hires |
| Crew turnover | ~110% annualized; 52% of new hires leave within 90 days |
| Seasonality | Coastal units (Costa Blanca, Costa del Sol, Balearics, Algarve) add +25% to +40% headcount from June to September |
| Workforce profile | Students, first jobs, second jobs, many part-time contracts; 30% non-Spanish nationals in coastal units; languages matter in tourist areas |

## 2. How hiring works today (as described by HQ, not yet validated)

1. A restaurant manager notices a gap ("we are short two people for weekend closes") and emails or WhatsApps the area HRBP.
2. The HRBP opens a requisition in the ATS **HireDesk**, which publishes to job boards and the careers page. Restaurants also have QR posters ("¡Únete al equipo!") that lead to the same ATS form.
3. Applications pile up in HireDesk. The central talent team (14 people) screens by CV when they have time. Most applicants have thin or no CV.
4. Shortlisted candidates get a phone call. Many do not answer unknown numbers.
5. The restaurant manager interviews in person. Scheduling happens over personal WhatsApp.
6. If hired, HR collects documents (ID/NIE, social security number, bank account, signed contract, food hygiene training certificate) by email. Contract registration and payroll setup happen in the HRIS **Nómina360**.
7. The manager adds the new hire to the rota in the scheduling tool **ShiftGrid**, often only after documents are complete.
8. The new hire completes mandatory modules in the training app **LearnBite** and shadows a crew trainer on the first shifts.

## 3. Systems landscape

| System | Category | Owner | Integration surface (simulated) |
|---|---|---|---|
| HireDesk | ATS | Talent Acquisition | REST API (requisitions, candidates, stages), webhooks on new application |
| Nómina360 | HRIS and payroll | People Ops / Payroll | REST API for employee creation; nightly CSV export; no webhooks |
| ShiftGrid | Workforce management (scheduling) | Operations | REST API for rotas and open shifts; publishes the weekly rota on Thursdays |
| TillCloud | POS | Finance / Ops | Read-only sales API at 15-minute granularity; labor forecast derived weekly |
| LearnBite | Training app (LMS) | Training team | Enrollment API, completion webhooks |
| Microsoft 365 | Email and calendar for HQ and managers | IT | Graph API (calendar for managers is used inconsistently) |
| WhatsApp | De facto channel for managers and crew | Nobody (shadow IT) | Personal numbers, group chats per restaurant |

## 4. Baseline metrics (last 12 months, company-operated units)

| Metric | Baseline |
|---|---|
| Median time from application to first contact | 3.8 days |
| Applicants never contacted | 41% |
| Interview no-show rate | 38% |
| Median time from verbal offer to first worked shift | 9 days |
| Day-1 no-show (hired but never shows up) | 18% |
| 90-day attrition of new hires | 52% |
| Manager time spent on hiring | ~6 hours per week per restaurant |
| Understaffed peak hours (labor below forecast) in July and August, coastal units | 7.5% of peak hours |
| Cost per hire (ads + HR time + manager time, internal estimate) | 420 EUR |
| Average drive-thru service time, understaffed vs fully staffed hour | 312 s vs 228 s |

## 5. Why now (the trigger)

- The CEO saw competitors announce AI agents for frontline hiring and wants a credible answer before the **summer 2027 campaign**, whose hiring starts in March 2027.
- Last summer, 11 coastal restaurants closed their drive-thru lane during peak hours on several weekends due to lack of staff.
- The People team's headcount is frozen for 2027.
- A labor inspection flagged inconsistent documentation timelines for new hires in two units.

## 6. The engagement

- **Buyer:** Chief People Officer.
- **Scope signed:** a 90-day paid pilot of an AI agent layer for crew hiring and onboarding in **12 company-operated restaurants in Alicante province (Costa Blanca)**, with 3 comparable restaurants as a control group.
- **Success criteria in the contract (to be refined in Phase 2):** faster time to first shift, fewer day-1 no-shows, less manager time on hiring, no drop in hiring quality, full GDPR compliance and auditability.
- **Constraints from IT:** no new app for crew or managers, no direct database access to client systems, all integrations through documented APIs, EU data residency.
- **Constraint from Operations:** managers will not log into another dashboard. Anything that needs a manager must reach them where they already are.

## 7. Cast of stakeholders (all fictional)

| Name | Role | What they care about | Likely objection |
|---|---|---|---|
| Marta Ibáñez | Chief People Officer (buyer) | Headcount frozen, summer readiness, employer brand | "Will candidates feel processed by a robot?" |
| Jordi Puig | Head of Talent Acquisition | Funnel speed, recruiter workload, ATS hygiene | "My team will lose control of who gets hired." |
| Raúl Sempere | Area Operations Director, Costa Blanca | Labor coverage at peak, service times, sales | "Hiring is HR's job, I need people on Saturday." |
| Yolanda Ferrer | Restaurant Manager, Benidorm Playa (drive-thru, 38 crew) | Not drowning in admin, reliable new hires | "I hire people I meet. I don't trust a CV or a bot." |
| Iker Lozano | Crew Trainer, Benidorm Playa | New hires who arrive prepared | "They show up without uniform or training done." |
| Hugo Andrade | Integration Lead, IT | Security, API limits, vendor sprawl | "Nómina360 has no webhooks and a fragile API." |
| Laura Cebrián | Data Protection Officer | GDPR, AI Act, retention, consent | "No automated decisions about people. Show me the logs." |
| Sofía Marques | People Ops and Payroll lead | Correct, complete documents before day 1 | "Half the documents arrive the night before." |
| Candidate personas | Applicants | A quick, human answer and a job that fits their life | Ghosting when the process is slow |
