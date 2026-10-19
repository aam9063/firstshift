# Transcript: Hugo Andrade, IT Integration Lead

- Role: Integration Lead, IT (Lumbre Burger Group HQ)
- Simulated date: 2027-02-11
- Duration: 38 minutes
- Context: Discovery interview about how client systems connect and what their limits are. Interviewer is an FDE researcher; open questions only, per `discovery/interview-guides.md` (IT Integration Lead).

---

[T-hugo-01] **Interviewer:** Thanks for making time, Hugo. To start, can you tell me a bit about your role and what you look after day to day?
[T-hugo-02] **Hugo Andrade:** Soy el responsable de integraciones de IT. Digamos que todo lo que tiene que hablar con otra cosa pasa por mi equipo. "If it has an API, it is my problem", as my team jokes.
[T-hugo-03] **Interviewer:** Walk me through the systems a new hire touches, from application to first payroll.
[T-hugo-04] **Hugo Andrade:** Vale. The candidate applies in HireDesk, that is the ATS, owned by Talent Acquisition. When they are hired, People Ops creates them in Nómina360, the HRIS and payroll system. Operations then puts them on the rota in ShiftGrid. Training enrols them in LearnBite. TillCloud is the tills, not really the new hire, but its sales data feeds the labour forecast that decides why we are hiring at all.
[T-hugo-05] **Interviewer:** And how do those systems talk to each other today?
[T-hugo-06] **Hugo Andrade:** Talk is generous. HireDesk has a decent REST API and webhooks for new applications, that works. Nómina360 has a REST API for employee creation and a nightly CSV export, no webhooks at all. ShiftGrid has an API for rotas and open shifts. LearnBite has an enrolment API and completion webhooks. And everything else travels by email or by people copying and pasting, sobre todo los managers con su WhatsApp.
[T-hugo-07] **Interviewer:** Which of those integrations work well today, and which are fragile?
[T-hugo-08] **Hugo Andrade:** HireDesk to the job boards works well, that is their core business. LearnBite enrolments are fine too. The fragile one is anything touching Nómina360. Every time someone asks me to connect something to it, I get nervous.
[T-hugo-09] **Interviewer:** Tell me more about that. What makes it fragile?
[T-hugo-10] **Hugo Andrade:** For one, it is an on-premise system behind our network, so every call goes through a gateway we maintain ourselves. And its behaviour is, cómo decirlo, creative.
[T-hugo-11] **Interviewer:** What are the hard limits of each system? Rate limits, webhooks, exports, that kind of thing.
[T-hugo-12] **Hugo Andrade:** HireDesk: generous rate limits, real webhooks, no problem. ShiftGrid: fine, though the rota only locks on Thursdays, so anything that wants tomorrow's rota is out of luck. LearnBite: small stuff. Nómina360 is the one with hard limits.
[T-hugo-13] **Interviewer:** What are Nómina360's limits exactly?
[T-hugo-14] **Hugo Andrade:** The API allows 60 requests per minute, and it is not a suggestion. Go over it and you get throttled, and their throttling behaviour is not what the documentation says.
[T-hugo-15] **Interviewer:** What happens when a request fails validation, for example an employee record with a bad field?
[T-hugo-16] **Hugo Andrade:** Aquí viene lo bueno. It returns HTTP 200. A success code. With an error body buried inside. So any client that just checks the status code thinks everything went fine, and the employee simply does not exist in payroll. We learned that one the hard way during the summer onboarding wave.
[T-hugo-17] **Interviewer:** That sounds painful. How do you work around it today?
[T-hugo-18] **Hugo Andrade:** Honestly? For reads we mostly stopped trusting the API. The nightly CSV export is the only reliable read we have. It is ugly, it is a file, but what is in the file is what is actually in the system.
[T-hugo-19] **Interviewer:** Tell me about the last integration incident and what it taught you.
[T-hugo-20] **Hugo Andrade:** Last July. A script a contractor wrote was creating employees via the API, checking the 200s, and reporting success. Three weeks later payroll finds dozens of people missing. All those "successes" were validation errors wrapped in 200s. We rebuilt their records from the CSV by hand. La lección: never trust that API's status codes, and never trust a write you cannot verify afterwards.
[T-hugo-21] **Interviewer:** What would you need to see before allowing a vendor to write into these systems?
[T-hugo-22] **Hugo Andrade:** First, everything through the documented APIs, no direct database access, ever. Second, EU data residency, non negotiable. Third, and this is the one vendors usually fail: every write must be idempotent and logged. If a job retries and creates the same employee twice, that is a payroll incident. And if I cannot see in a log exactly what was written, when, and by whom, the answer is no.
[T-hugo-23] **Interviewer:** What makes a write idempotent in practice, for you?
[T-hugo-24] **Hugo Andrade:** A key I control. If the same onboarding arrives twice with the same identifier, the second call updates or no-ops, it does not duplicate. And the log has to be queryable by that key so I can audit any single person end to end.
[T-hugo-25] **Interviewer:** How do the managers' tools fit into your world, things like WhatsApp or personal phones?
[T-hugo-26] **Hugo Andrade:** WhatsApp is shadow IT as far as I am concerned, nadie lo controla. Personal numbers, personal groups per restaurant. I cannot back it up, audit it or turn it off. It works, and that is exactly the problem.
[T-hugo-27] **Interviewer:** If a new tool came in for hiring, what would make it easy for you to accept versus hard?
[T-hugo-28] **Hugo Andrade:** Easy: no new app for the crew or managers, documented APIs, EU hosting, clean logs. Hard: anything that wants a database connection, or that generates writes into Nómina360 without telling me exactly what it writes and when.
[T-hugo-29] **Interviewer:** Last question: what did I not ask that I should have?
[T-hugo-30] **Hugo Andrade:** You did not ask who gets called at 3 a.m. when an integration breaks. It is me. So whatever comes next, I want monitoring and alerts on those writes, not a phone call from payroll on payday. Y quizá café. Mucho café.

## Interviewer notes

- **What surprised me:** Nómina360 returns HTTP 200 with an error body on validation failures, has a 60 requests per minute limit, and the nightly CSV is the only reliable read [T-hugo-14 to T-hugo-22].
- **What contradicts HQ's description:** HQ presents the integration surface as routine REST APIs; in practice one of the two most critical systems is read-mostly, fragile on writes, and any vendor write must be idempotent and logged to be acceptable [T-hugo-22].
- **What I still do not know:** whether HireDesk webhooks are at-least-once or at-most-once, and who owns the reconciliation when the nightly CSV disagrees with what we wrote during the day.
