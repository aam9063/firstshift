# Transcript: Sofía Marques, People Ops and Payroll lead

- Role: People Ops and Payroll lead (Lumbre Burger Group HQ)
- Simulated date: 2027-02-13
- Duration: 31 minutes
- Context: Discovery interview about what payroll needs before a new hire can start. Interviewer is an FDE researcher; open questions only, per `discovery/interview-guides.md` (People Ops and Payroll lead).

---

[T-sofia-01] **Interviewer:** Thanks for sitting down with me, Sofía. Can you start by describing what your team looks after?
[T-sofia-02] **Sofía Marques:** Claro. Mi equipo hace de todo un poco: contracts, altas y bajas en nómina, documents, benefits, y las consultas de los restaurantes cuando algo no cuadra. Payroll for nearly ten thousand crew across two countries, with a team of six. Summer is our marathon.
[T-sofia-03] **Interviewer:** Walk me through what you need before you can register a new employee.
[T-sofia-04] **Sofía Marques:** The full pack: signed contract, ID or NIE, social security number, bank account certificate, and the food hygiene training certificate. Without those I cannot create the employee in Nómina360, and without Nómina360 there is no payroll, no alta en la Seguridad Social, nothing.
[T-sofia-05] **Interviewer:** What happens once you have the complete pack?
[T-sofia-06] **Sofía Marques:** I register them in Nómina360, then payroll runs on its cycle. If everything arrives before the cutoff, the first payslip is normal. If it does not, we are doing manual payments or corrections later, and every correction is an hour of my team's time and a person who does not trust us in week one.
[T-sofia-07] **Interviewer:** How do documents arrive to you today?
[T-sofia-08] **Sofía Marques:** Email, mostly. Photos taken with the phone, sometimes sideways, sometimes blurred. Some managers collect paper and scan it in batches on Friday afternoons. Occasionally someone brings it to the restaurant and it sits in a drawer for a week. Cada restaurante lo hace de una forma distinta.
[T-sofia-09] **Interviewer:** Which documents arrive late most often, and what does that cost you?
[T-sofia-10] **Sofía Marques:** The same three, always. El certificado bancario, el número de la Seguridad Social y el certificado de manipulación de alimentos. Bank account, social security number, food hygiene certificate. ID and contract usually come because the candidate has them in hand. The other three depend on a bank appointment, a government office and a training course, so they lag.
[T-sofia-11] **Interviewer:** What does that lateness actually cost?
[T-sofia-12] **Sofía Marques:** Two things. Chasing: my team sends the same reminder email three or four times per hire, per document. And starts: a person who could be working is sitting at home because a certificate is missing. In summer that is dozens of people at once.
[T-sofia-13] **Interviewer:** Tell me about the last person who could not start on time because of paperwork.
[T-sofia-14] **Sofía Marques:** A girl in Alicante, hired on the Tuesday, meant to start on the Saturday. Everything was ready except the food hygiene certificate. The course she took did not issue the certificate until the following Wednesday. Five days of a signed contract, a manager waiting, and a restaurant short one person on a weekend. Nadie tuvo la culpa y aun así nadie empezó.
[T-sofia-15] **Interviewer:** How do you chase missing documents today?
[T-sofia-16] **Sofía Marques:** I keep a spreadsheet with flags, and my team sends template emails. When that fails, we call the restaurant manager, and the manager calls or messages the person on WhatsApp. So the chase goes through three people and depends on whoever answers fastest.
[T-sofia-17] **Interviewer:** What does "ready to start" mean for you, exactly?
[T-sofia-18] **Sofía Marques:** Registered in Nómina360, alta done with the Seguridad Social, contract signed, and the mandatory documents complete. Until all of that is true, for me the person is not an employee, they are a promise. Managers see it differently, of course. Ellos quieren a la gente el sábado.
[T-sofia-19] **Interviewer:** How do managers see it differently?
[T-sofia-20] **Sofía Marques:** They sometimes put people on the rota before I have registered them. I understand why, they are short. But then the person works four shifts and there is no alta, and if there is an accident, that is a serious problem for everyone. We have had that conversation more than once.
[T-sofia-21] **Interviewer:** What about people who never hand in the last document at all?
[T-sofia-22] **Sofía Marques:** It happens, especially the hygiene certificate. We end up with people who worked a week or two and were never registered, because the rota went ahead. Then I have to regularise it retroactively, which is exactly as fun as it sounds.
[T-sofia-23] **Interviewer:** What does your volume look like across the year?
[T-sofia-24] **Sofía Marques:** Around eleven thousand hires a year, and in June and July it is a wave. My team goes from steady to drowning. Every incomplete pack is a follow-up, and the follow-ups do not shrink, they multiply.
[T-sofia-25] **Interviewer:** If the document chase worked differently, what would change for you?
[T-sofia-26] **Sofía Marques:** If the documents arrived complete, checked, and in one place, with me knowing what is missing the same day it is missing, my team could go from chasing to registering. That is the difference between six people putting out fires and six people keeping payroll clean.
[T-sofia-27] **Interviewer:** What would make you say no to a change in this process?
[T-sofia-28] **Sofía Marques:** Anything that adds steps for my team, or that lets documents into the process without being checked. I would rather have fewer documents, correct, than more documents, doubtful. Y nada de sistemas nuevos que nadie mantiene en enero.
[T-sofia-29] **Interviewer:** Last question: what did I not ask that I should have?
[T-sofia-30] **Sofía Marques:** You did not ask what happens when a document is wrong, not just late. A wrong bank account number means a failed payment, an angry new hire, and a manual fix. Checking the document at the moment it arrives, not at payday, would save us more than any chasing tool.

## Interviewer notes

- **What surprised me:** the late documents are always the same three (bank account certificate, social security number, food hygiene certificate), which makes pre-collection of exactly those three a testable design move [T-sofia-10].
- **What contradicts HQ's description:** HQ describes document collection as a step after the offer; in practice payroll registration and the rota are blocked by documents that could be collected earlier with consent [T-sofia-10, T-sofia-16].
- **What I still do not know:** the precise field list Nómina360 needs for employee creation, and whether validation can run before contract signature without creating an employee record.
