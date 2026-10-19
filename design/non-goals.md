# Non-goals: crew hiring pilot

- **Phase:** 2, problem framing (spec: `specs/02-problem-framing.md` section 6).

What FirstShift will explicitly not do in the pilot, and why.

| # | Non-goal | Reason (one line) |
|---|---|---|
| 1 | Automated rejection of candidates | GDPR article 22 and the DPO's line: a human sees the facts and decides; the agent recommends and drafts, a person signs ([T-laura-18, T-laura-20], [T-jordi-22]). |
| 2 | Salary negotiation | Salary is a People Ops policy variable, not a conversation the agent should have; candidates want it stated early and plainly, which is a data fix, not a negotiation ([T-candidate-b-20], [T-candidate-a-26]). |
| 3 | Replacing HireDesk (the ATS) | HireDesk stays the requisition and application system of record; FirstShift is an agent layer on its documented API, and replacing an ATS in 90 days is a different project with a different buyer ([T-hugo-06], brief section 3). |
| 4 | Building a scheduling engine | ShiftGrid already owns the rota and its API; the gap is that new hires cannot be scheduled until Nómina360 finishes, not that scheduling is missing ([T-hugo-04], [T-yolanda-20]). |
| 5 | Performance management of existing crew | The pilot covers hiring and onboarding to first productive shift; monitoring crew performance is a different data domain with its own works-council and GDPR weight, out of scope by contract (brief section 6). |
| 6 | Franchisee rollout during the pilot | The pilot is 12 company-operated units in Alicante province (brief section 6); the design stays multi-tenant ready so franchisees can join later, but none are onboarded now. |
| 7 | Voice interviews in v1 | WhatsApp text with quick replies matches how candidates and managers already behave and keeps every word auditable; voice adds transcription, consent and quality risk with no evidence of demand. Revisit as a v2 candidate once text is proven. |
| 8 | Replacing managers' personal WhatsApp with a ban | Managers' "maybes" behavior will not stop by decree [T-laura-24]; FirstShift adopts the bench with consent and logging instead of fighting it, and the personal channel is retired by displacement, not policy. |
| 9 | New forecast or labor-demand models | TillCloud sales feed the weekly forecast and managers overwrite it anyway [T-raul-18]; fixing forecasting is an Ops project, and the pilot only needs coverage measured consistently (metric tree measurement note). |
