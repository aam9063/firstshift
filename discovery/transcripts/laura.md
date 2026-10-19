# Transcript: Laura Cebrián, Data Protection Officer

- Role: Data Protection Officer (Lumbre Burger Group HQ)
- Simulated date: 2027-02-12
- Duration: 34 minutes
- Context: Discovery interview about where candidate data lives, retention and compliance risk. Interviewer is an FDE researcher; open questions only, per `discovery/interview-guides.md` (DPO).

---

[T-laura-01] **Interviewer:** Thanks for your time, Laura. Could you start by telling me about your role and what a normal week looks like for you?
[T-laura-02] **Laura Cebrián:** Claro. Soy la delegada de protección de datos del grupo. I review processing activities, handle DPIAs, answer access requests, and mostly chase departments that have invented a new spreadsheet with personal data in it. A quiet week is a myth.
[T-laura-03] **Interviewer:** Walk me through where candidate data lives today and who can see it.
[T-laura-04] **Laura Cebrián:** The formal home is HireDesk, the ATS. Requisitions, CVs, stages, notes. That at least has access controls. Then there is the informal layer, and the informal layer is bigger than the formal one.
[T-laura-05] **Interviewer:** What do you mean by the informal layer?
[T-laura-06] **Laura Cebrián:** CVs forwarded to personal email. Printed CVs handed at the counter that someone photographs. Spreadsheets of summer candidates. And WhatsApp: los managers mantienen conversaciones con candidatos en sus números personales, en grupos del restaurante. Names, phone numbers, sometimes a photo of an ID document someone sent to prove who they are. All of that is candidate data, and none of it is in HireDesk.
[T-laura-07] **Interviewer:** What happens to rejected candidates' data?
[T-laura-08] **Laura Cebrián:** In theory there is a retention policy. In practice, HireDesk keeps candidate records forever by default. Nobody configured deletion, and nobody owns the job. Two years ago I asked for a purge and got a list of exceptions so long that it never happened.
[T-laura-09] **Interviewer:** Forever by default. How did that come about?
[T-laura-10] **Laura Cebrián:** Nobody decided it, that is the point. It is the absence of a decision. The ATS default was never changed, Talent Acquisition is afraid of deleting someone useful for next summer, and there is no tooling to apply retention rules selectively. So everything stays. Es la realidad, aunque no me gusta decirla en voz alta.
[T-laura-11] **Interviewer:** And the WhatsApp messages managers keep, what is your view on those?
[T-laura-12] **Laura Cebrián:** It is my biggest headache in hiring. Personal numbers, personal devices, no way for me to know what exists, no way to answer a data subject access request properly. If a candidate asks us to delete their data, I can act on HireDesk, but the conversation in some manager's WhatsApp? I cannot even find it. No puedo borrar lo que no sé que existe.
[T-laura-13] **Interviewer:** Where would you say the biggest compliance risk in the current process is?
[T-laura-14] **Laura Cebrián:** Two things compete. One is retention: data kept forever with no defensible schedule. The other is the shadow channel: hiring decisions and personal data flowing through personal WhatsApp with zero governance. If I had to pick one for an inspector, I would pick the WhatsApp one, because it also touches special situations we do not even track.
[T-laura-15] **Interviewer:** You mentioned the labour inspection flag last year. What did it involve?
[T-laura-16] **Laura Cebrián:** Documentation timelines for new hires, two units on the coast. Not primarily a data protection finding, but it exposed how undocumented our flows are. If we cannot show when a document was received or requested, that is a problem for them and for me.
[T-laura-17] **Interviewer:** What would a compliant, assisted process need to show you?
[T-laura-18] **Laura Cebrián:** Four things. A record of lawful basis for every candidate, with consent captured at the right moment and versioned. Retention rules that actually execute, not a PDF policy. An audit trail: who saw what, what was decided, when, and on what grounds. And no automated decisions about people. Assist, yes. Decide, no. Show me the logs and I can sleep.
[T-laura-19] **Interviewer:** When you say no automated decisions, where exactly is the line for you?
[T-laura-20] **Laura Cebrián:** The line is simple: a human sees the relevant facts and decides. If a system ranks or filters people and a human never meaningfully reviews the ones it excluded, that is a decision about people. If it helps a human read faster and the human decides, I can live with that, provided I can audit it.
[T-laura-21] **Interviewer:** What would make you say no to a new tool in this space?
[T-laura-22] **Laura Cebrián:** Data leaving the EU. Vendors who cannot name their subprocessors. Tools that cannot delete on request, end to end. And anything that would push even more candidate conversations into personal WhatsApp. Eso es dar un paso atrás.
[T-laura-23] **Interviewer:** Interesting, you said a step back. How do you see the current WhatsApp situation, could it get better?
[T-laura-24] **Laura Cebrián:** Look, I am realistic. You will not make managers stop using WhatsApp by telling them not to. But if those conversations moved to a channel the company governs, where I can fulfill an access request and apply retention, for me that is not a risk, that is a compliance improvement. Today I have zero visibility. Something governed, even imperfect, is more than I have now.
[T-laura-25] **Interviewer:** What about consent for messaging candidates directly, for example by WhatsApp?
[T-laura-26] **Laura Cebrián:** It needs to be explicit, captured with timestamp and the version of the notice they saw, and honoured for every channel. If we message someone on WhatsApp who only consented to email, that is a finding waiting to happen. The mechanics matter less than being able to prove it.
[T-laura-27] **Interviewer:** Last question: what did I not ask that I should have?
[T-laura-28] **Laura Cebrián:** You did not ask who signs off. Any new processing in hiring needs a DPIA and my signature before a single candidate touches it, not after the pilot. And ask me about deletion someday: it is the hardest problem here and everyone treats it as an afterthought.

## Interviewer notes

- **What surprised me:** she would treat a governed messaging channel as a compliance improvement rather than a risk, because today candidate data lives in managers' personal WhatsApp [T-laura-24].
- **What contradicts HQ's description:** HQ worries mostly about new-tool risk; the existing state (forever-by-default retention in HireDesk, ungoverned personal channels) is already the bigger exposure [T-laura-14, T-laura-18].
- **What I still do not know:** the exact retention period she would accept for rejected and benched candidates, and whether automated matching suggestions (not decisions) fall inside her reading of article 22.
