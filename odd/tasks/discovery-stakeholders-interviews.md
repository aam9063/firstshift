# Feature: F02 discovery-stakeholders-and-interviews

## Header

- **Objective:** evidence-based discovery for Lumbre Burger Group: stakeholder map, simulated verbatim interviews, ride-along observation, per the FDE principle that the WhatsApp groups describe the process.
- **Status:** closed, awaiting human review before F03
- **Next step:** F03 discovery-process-systems-funnel after human review.

## Specs

Source of truth: `specs/00-client-brief.md` and `specs/01-discovery.md` sections 1, 2 and 3. Quote of the governing rules:

- S1 (01-discovery, section 2): "Each simulated stakeholder is played by a separate agent instance briefed only with their row in `00-client-brief.md` section 7, the company snapshot and a hidden "private truth" (below). The interviewer agent does not see the private truth."
- S2 (01-discovery, section 2): "The interviewer uses `discovery/interview-guides.md`: open questions, "walk me through the last time...", no leading questions, no solution pitching."
- S3 (01-discovery, section 2): "Transcripts are saved verbatim. Every later claim about the client must cite a transcript line (`[T-yolanda-14]`) or a data file."
- S4 (01-discovery, section 2): "After each interview, the interviewer writes 3 bullets: what surprised me, what contradicts HQ's description, what I still do not know."
- S5 (01-discovery, outputs): `discovery/stakeholder-map.md` (power/interest grid, decision rights), `discovery/interview-guides.md` (one guide per stakeholder role), `discovery/transcripts/*.md` (one per stakeholder in the brief, plus 3 candidates and 1 churned new hire), `discovery/ride-along-benidorm.md`.
- S6 (01-discovery, section 3): "Write `discovery/ride-along-benidorm.md` as a timestamped log of a Saturday at Benidorm Playa from 07:30 to 23:30, observing Yolanda. It must show, with times: when hiring tasks interrupt operations, which channel each interaction uses (personal WhatsApp, phone, email, HireDesk, ShiftGrid), every copy-paste between systems, and every moment a candidate waits for a human. End with a count of hiring-related interruptions and minutes."
- S7 (01-discovery, exit): every stakeholder in the brief has a transcript and a stakeholder-map entry; interviewer notes have the 3 required bullets; no code.

## Constraints

- The interviewer (parent session) must not read the private truths: workers receive only their role brief + private truth; interview plans go out without truths; worker outputs include transcript + post-notes, not truth summaries.
- Repository artifacts in English, conversations with simulated people may be in Spanish (verbatim quotes stay Spanish).
- No em dash in any file.

## Tasks

| ID | Spec | Task | Status |
|---|---|---|---|
| T1 | S1,S2 | Interview guides per role + worker role-play briefs (private truths distributed) | done |
| T2 | S1,S3 | 12 role-played interview transcripts with line IDs | done |
| T3 | S4 | Interviewer post-notes per transcript (3 bullets) | done |
| T4 | S6 | ride-along-benidorm.md with interruption count | done |
| T5 | S5 | stakeholder-map.md with decision rights and evidence links | done |
| T6 | S7 | Verify exit criteria, close feature | done |

## Open questions

- None. Yolanda's Nómina360 wait (3-6 days) was already known from the spec's private truth and is now interview evidence.

## Log

- L1 (user request, verbatim): "ya esta todo merge. continua"
- L2: env.example was lost in the GitHub merge resolution; restored in this branch.
- L3: Role-play delegated to 4 parallel workers (restaurant, HQ, systems, candidates), each with only its stakeholders' brief rows and private truths; the interviewer notes are written afterwards from the transcripts only.
- L4: Slice boundary: commit 415c7dc holds 924 authored lines (transcripts are inherently long); the feature is one PR, no further slicing needed. stakeholder-map delegated to a worker after the context backstop fired.
- L5: Exit verification evidence: 12 transcripts (8 brief stakeholders + 3 candidates + 1 churned hire); every transcript has exactly 3 interviewer bullets (grep verified); 0 em dashes in discovery/; stakeholder-map cites line IDs from all 12 transcript sources, zero missing citations (worker grep + spot check); ride-along ends with 13 interruptions, ~105 minutes, 4 copy-pastes, 7 candidate waits; Mermaid quadrant in the map uses valid quadrantChart syntax.
- L6: The interviews established the expected discovery direction with evidence: first-contact speed decides the hire ([T-candidate-a-08..12]), availability is a dead dropdown field ([T-candidate-b-10, T-candidate-c-20]), the hired-to-rota gap in Nómina360 is the biggest sink and nobody owns it ([T-yolanda-20, T-hugo-14..22]), managers run an informal pool the system ignores ([T-yolanda-14..18]), week-1 attrition is expectation mismatch and rota conflict ([T-iker-13..16, T-churned-16..24]).
