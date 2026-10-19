# 01 · Discovery: understand how work really happens

**Goal:** replace HQ's description of the hiring process (`00-client-brief.md`, section 2) with an evidence-based picture of how work actually flows between people, systems and channels, and quantify where time, candidates and money are lost.

**FDE principle for this phase:** the org chart describes ownership, the WhatsApp groups describe the process. Assume the documented process is wrong until a transcript or a data sample proves it.

**Outputs (all in `discovery/`):**

| File | Content |
|---|---|
| `discovery/stakeholder-map.md` | Power/interest grid, decision rights, who can block the pilot |
| `discovery/interview-guides.md` | One guide per stakeholder role |
| `discovery/transcripts/*.md` | Simulated interview transcripts (one per stakeholder in the brief, plus 3 candidates and 1 churned new hire) |
| `discovery/ride-along-benidorm.md` | Simulated "day in the restaurant" observation log |
| `discovery/as-is-process.md` | As-is swimlane (Mermaid) with handoffs, delays and failure points |
| `discovery/systems-and-data.md` | System inventory, data objects, ownership, API capabilities and gaps |
| `discovery/funnel-baseline.md` | Funnel with drop-off at each stage, computed from mock data |
| `discovery/pain-points.md` | Ranked pain points with evidence links and cost estimate |
| `discovery/insights.md` | 5 to 8 non-obvious insights, each with "so what" for design |

---

## 1. Stakeholder map

Place every stakeholder from the brief on a power/interest grid and add, for each:
- Decision rights over the pilot (approve, veto, influence, inform).
- What a win looks like for them in their own words.
- The evidence they would need to say yes.
- The communication channel and cadence they prefer.

Explicitly identify: the **economic buyer** (Marta), the **day-to-day champion** to recruit (hypothesis: Raúl, because understaffing hurts his sales), the **technical gatekeeper** (Hugo), the **compliance gatekeeper** (Laura) and the **end users whose behavior must change** (Yolanda and the managers).

## 2. Simulated interviews

The engagement has no real client, so interviews are simulated with role-play. Rules to keep them useful and honest:

1. Each simulated stakeholder is played by a separate agent instance briefed only with their row in `00-client-brief.md` section 7, the company snapshot and a hidden "private truth" (below). The interviewer agent does not see the private truth.
2. The interviewer uses `discovery/interview-guides.md`: open questions, "walk me through the last time...", no leading questions, no solution pitching.
3. Transcripts are saved verbatim. Every later claim about the client must cite a transcript line (`[T-yolanda-14]`) or a data file.
4. After each interview, the interviewer writes 3 bullets: what surprised me, what contradicts HQ's description, what I still do not know.

**Private truths** (only for the role-play agents; they reveal them only if asked well):

| Stakeholder | Private truth |
|---|---|
| Yolanda (Restaurant Manager) | She keeps a personal WhatsApp list of ~25 "maybes" (ex-employees, friends of crew, walk-ins) and hires from it before anyone in HireDesk. She never logs these hires in HireDesk until HR forces her to. Her real bottleneck is that a hired person cannot be put on the rota until Nómina360 creates them, which takes 3 to 6 days. |
| Iker (Crew Trainer) | New hires often arrive without the food hygiene module done, so they cannot touch food on day 1 and he has to keep them on the till or cleaning. Two of the last five quit in week 1 saying "this is not what I was told". |
| Jordi (Head of TA) | His team screens ~30% of applicants. They prioritize "complete CVs", which in practice deprioritizes students and first-job applicants, the exact profile that converts best for weekend shifts. He knows HireDesk data is dirty. |
| Raúl (Area Ops) | He does not trust the labor forecast in ShiftGrid; managers overwrite it. But he knows exactly which units will break in July because it happens every year. |
| Hugo (IT) | Nómina360's API has a 60 requests per minute limit and returns 200 with an error body on validation failures. A nightly CSV is the only reliable read. He would accept a vendor that writes via API if every write is idempotent and logged. |
| Laura (DPO) | Candidate data in HireDesk is kept forever by default. She is worried about WhatsApp personal numbers of managers holding candidate data. She would see a governed channel as a compliance improvement, not a risk. |
| Sofía (Payroll) | The documents that arrive late are always the same three: bank account certificate, social security number, food hygiene certificate. |
| Marta (CPO) | The board asked her for "AI in HR" by Q1. She fears a public backlash if a candidate posts screenshots of a rude bot. |
| Candidate A (student, 19, Alicante) | Applied to 6 chains in one evening via QR codes. Took the first one that answered on WhatsApp within the hour. |
| Candidate B (Moroccan national, 34, NIE in hand, second job) | Can only work evenings after 18:00 and weekends. Was rejected twice for "availability" without anyone asking which shifts. |
| Candidate C (Portuguese, 22, seasonal in Benidorm) | Speaks Portuguese, Spanish and English. Was never asked about languages, which the drive-thru in a tourist area needs. |
| Churned new hire (left on day 4) | Did not get the first rota until the night before, the shift clashed with university, and nobody answered when she asked to swap. |

## 3. Ride-along (simulated observation)

Write `discovery/ride-along-benidorm.md` as a timestamped log of a Saturday at Benidorm Playa from 07:30 to 23:30, observing Yolanda. It must show, with times: when hiring tasks interrupt operations, which channel each interaction uses (personal WhatsApp, phone, email, HireDesk, ShiftGrid), every copy-paste between systems, and every moment a candidate waits for a human. End with a count of hiring-related interruptions and minutes.

## 4. As-is process map

Produce a Mermaid swimlane-style flowchart with lanes: Candidate, Restaurant Manager, Talent team, People Ops/Payroll, Crew Trainer, Systems (HireDesk, Nómina360, ShiftGrid, LearnBite). Mark:
- Handoffs between lanes (where work waits).
- **Shadow paths** (Yolanda's "maybes" list, personal WhatsApp).
- Elapsed time per step (median, from mock data or transcripts).
- The 3 longest waits and the 3 highest drop-off points, highlighted.

Then write one paragraph: "The process HQ described vs the process that actually runs".

## 5. Systems and data inventory

For each system: data objects (requisition, candidate, application, stage, employee, shift, open shift, enrollment, completion), source of truth for each object, read and write capabilities, latency, rate limits, auth, known quirks (from Hugo's transcript), and **who would need to approve write access**.

End with a "data object ownership" table. The key finding to look for: **no system owns the transition from "hired" to "on the rota"**. If the analysis finds something different, report what the evidence says.

## 6. Funnel baseline from mock data

Generate a mock dataset for the 15 pilot and control restaurants for the last 6 months (seeded, reproducible: `mocks/seed/` with a fixed random seed), consistent with the baseline table in the brief. Compute the funnel:

Applied → Contacted → Screened → Interview scheduled → Interview attended → Offer → Documents complete → On rota → Day 1 worked → Day 30 active → Day 90 active.

Show counts, conversion per stage and median elapsed time between stages. Highlight the largest absolute loss of candidates and the largest time sink.

## 7. Pain points and insights

`pain-points.md`: rank by (frequency x impact on labor coverage x cost). Each pain point cites evidence and an estimated annual cost for the 12 pilot restaurants, with the formula shown.

`insights.md`: 5 to 8 insights that are **non-obvious and actionable**. Format each as:

> **Insight:** ...
> **Evidence:** transcript and data references
> **So what for design:** ...

Expected direction (validate or refute, do not assume): speed of first contact decides who wins the candidate; availability is collected as a vague field instead of matched to real rota gaps; the hired-to-rota gap is the biggest time sink and nobody owns it; managers already run an informal talent pool that the system ignores; first-week attrition is driven by expectation mismatch and rota conflicts, not by the job itself.

## Exit criteria

- [ ] Every stakeholder in the brief has a transcript and a stakeholder-map entry.
- [ ] As-is map renders and shows shadow paths and the 3 worst waits.
- [ ] Funnel computed from seeded data with a script that can be re-run (`uv run python -m mocks.funnel`).
- [ ] At least 5 insights, each with evidence references that resolve to real files.
- [ ] A one-paragraph "discovery readout" at the top of `discovery/insights.md` that the CPO could read in 60 seconds.
