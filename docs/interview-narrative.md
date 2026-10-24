# Interview narrative (English, written to be spoken)

Companion to `docs/case-study.md`. Every number is either a baseline
assumption from the fictional brief or a simulated outcome, and each results
sentence says which. The bridge section is an explicit placeholder: it ships
empty until the author supplies the real details. Nothing about the author or
the target company is invented here.

## The 30-second version

"I simulated a full Forward Deployed Engineering engagement for a fictional
fast-food chain: discovery inside the client, a reframe of their ask, a
working AI agent system, and a measured pilot. Their stated problem was
screening candidates faster; discovery showed the real problem was the gap
between a signed hire and a first worked shift. I built FirstShift, three
WhatsApp agents around a deterministic core that never lets the LLM make a
hiring decision. In the simulated day-30 pilot, 726 applications through the
real pipeline reached a 100% contact rate versus 58% in the control model,
and the median application-to-first-shift time dropped from 26.4 to 6.3
simulated days. All simulated, with the evidence trail in the repo."

## The 2-minute version (STAR)

**Situation.** A fictional Iberian quick-service group: 310 restaurants,
about 11,000 hires a year, 52% of new hires gone within 90 days, and coastal
units adding up to 40% headcount every summer. The trigger was the summer
campaign, and the signed engagement was a 90-day paid pilot in 12 restaurants
with 3 controls.

**Task.** My charter was a crew-hiring pilot for summer readiness, with the
client's stated pain framed as "we need to screen applicants faster".

**Action.** Discovery changed the problem. Three findings did the work:
41% of applicants were never contacted, and candidates take the first chain
that answers; the largest time sink was not screening but the unowned window
between verbal yes and first schedulable shift, 5.1 median days; and managers
already ran an informal talent pool of "maybes" on personal WhatsApp,
invisible to every system. So I reframed the ask from "screen faster" to
"time to first productive shift" and built FirstShift: three agents (Recruit,
Onboard, Pulse) talking to candidates and managers on WhatsApp around a
deterministic state machine. The LLM only talks, extracts schema-validated
data and summarizes; eligibility, timers and every transition are plain
Python, offers require a recorded human approval, and every write to the
client's ATS, HRIS and scheduling system goes through an outbox with retries
and a dead-letter queue. I iterated with an eval harness: 44 synthetic
personas, deterministic guardrail checks, one measured change per iteration,
keep or revert on the exact metric, and I fixed four measured defects along
the way, including internal identifiers leaking into candidate messages (39
conversations to 0) and duplicate consent asks (44 conversations to 0).

**Result.** In the simulated day-30 pilot, 726 applications ran through the
real pipeline against a statistical control arm: contact rate 100% versus
58%, median application to first shift 6.3 versus 26.4 simulated days, and
zero deterministic guardrail failures across the run. The simulation also
produced honest failures that became client decisions: 156 simulated hires
were scheduled and still did not show up on day 1, and manager decision SLA
breaches were the throughput bottleneck. Everything is labelled simulation
and traceable in the repo. One thing I would do differently: the eval judge
turned out to be a weak instrument, its agreement with human labels was 17%
exact, so I learned to anchor keep/revert decisions on deterministic checks
first and treat judge scores as noise.

## Bridge to my real experience

At Softtek, a consultancy, one of my clients is a large IBEX 35 steel
manufacturer digitising its R&D. I work on a computer vision project: the
client's engineers train AI models with tools such as ClearML and Voxel51 to
identify what a steel sheet is made of from a microscope image, and my team
builds the frontend and backend platform around those models. They train the
models; we build the platform they live in.

Working with those engineers I saw how much time they lost entering
hyperparameters by hand or writing YAML files manually. It was slow and
repetitive, and it took them away from the work that actually needs an
engineer. I proposed a tool inside the platform that generates ready-to-
download YAML files and can also import the ones that already exist. I did
the technical spike and, working from detailed specs and acceptance criteria
with an AI coding agent, built a fast prototype for my team and the client.
The agent proposed and I decided what shipped. When the client approved it
I built the final version, checking everything against the
acceptance criteria, and shipped it to production through our Azure DevOps
pipelines.

The client liked the prototype and asked for more functionality than I had
planned, so the final tool ended up bigger than the first plan. It is fully
integrated in the platform and the client's engineers use it today; the
client has also confirmed plans for similar tools elsewhere in the
application.

What transfers to FirstShift:

- I found the real need by watching users work, not by reading a ticket,
  which is exactly what the discovery phase of this repository simulates.
- I shipped an internal tool end to end, from spike to production, with
  direct client contact and a CI/CD pipeline.
- I used AI to accelerate implementation while the decisions, the acceptance
  criteria and the final review stayed mine, the same ODD discipline this
  repository is built with: specs first, AI proposes, the human decides.
- The lesson I carry: a fast prototype in front of the client is the quickest
  way to find the real requirement, and the AI accelerates you but your
  judgement is what makes the result good.

## Relevance to the target company (public facts only)

Frame FirstShift as "how I would think about a deployment like the ones you
run", never as a critique or a replacement. The only facts referenced about
the company are public: it builds AI agents for frontline workforce
management with named agents covering recruiting, onboarding, and engagement
and retention; its agents reach workers through WhatsApp, SMS and voice
because frontline workers often have no corporate email; public reporting
lists large restaurant and retail groups among its customers, including
operators of major fast-food brands, and the company raised a Series A in
June 2026. No inside knowledge is claimed anywhere in this document.

## Likely questions and crisp answers

1. **How did you decide what to build first?** Discovery ranked pain by
   impact on labor coverage, and I shipped the smallest end-to-end slice
   first: one candidate from webhook to scheduled first shift on mocks, then
   the console, then evals, then hardening. The bench, referrals and voice
   were deliberately out of pilot scope.
2. **How do you keep an LLM from making hiring decisions?** It cannot. A
   plain-Python state machine owns every transition, eligibility check and
   timer; the LLM only converses, extracts into Pydantic models that are
   validated or re-asked, and summarizes. A red-team case proves an offer
   cannot fire without a recorded human approval.
3. **What happens when the client's HRIS has no webhooks?** That is the
   real design, not the exception: Nómina360, the fictional HRIS, has no
   webhooks, so FirstShift polls, tracks the 3-to-6-day employee creation in
   a promise-to-payroll tracker, and treats a nightly CSV export as the
   reconciliation truth that can downgrade any API write that did not land.
4. **How would you get a skeptical restaurant manager to use it?** Do not
   give her a tool: meet her in WhatsApp, where she already hires from her
   "maybes" list. The system starts by doing what she does today, imports
   her bench with consent, and asks for decisions as buttons, not logins.
   Discovery quotes the objection to beat: "I don't trust a CV or a bot."
5. **How do you know the agents are not biased?** I measure it: the eval
   suite reports a fairness table across language and age-band proxies with
   a four-fifths rule threshold, and the simulated pilot flagged no group
   below 0.95 selection ratio. Real deployment adds the DPO-reviewed
   criteria and human decisions on every consequential step.
6. **What would you measure in the first week of a real pilot?** First
   contact under 5 minutes for 95% of applicants (the SLO), manager decision
   SLA breaches, day-1 show rate, and how many hires reach documents-
   complete without human chasing. Those four map directly to the simulated
   failure modes.
7. **What did you get wrong, and how did evals show it?** The first
   screening message asked three questions at once and the transcript leaked
   an internal identifier to a candidate; the calibration read and the
   transcripts showed both, and measured iterations took each defect to 0. I
   also got the judge wrong: I trusted judge means until three identical
   runs disagreed more than my iteration's effect.
8. **How do you work with AI coding agents without losing control of
   quality?** Specs as source of truth, one feature document per
   substantial change, test-first on the core, and evidence-based
   checkoffs: a task is not done because the agent says so, it is done when
   a named command or report proves it.
9. **Why WhatsApp and not an app?** Because that is where the work already
   happens: managers run hiring on personal WhatsApp and half of candidates
   will not answer unknown numbers. A new app adds a adoption problem to a
   speed problem.
10. **What is different about deploying for a franchisee versus
    company-operated units?** Ownership and data. Franchisees run their own
    HR, so consent, criteria and the bench belong to them; the fictional
    group's 18% franchised units may opt into central tools. Company-operated
    units let Talent own criteria centrally; franchisee rollout needs a
    separate data agreement and local owner first.
11. **What does the pilot simulation not prove?** People. Managers are
    scripted, so approvals are instant and interviews are always attended;
    the 72 decision SLA breaches in 30 simulated days are the one human
    queue it does stress. Before launch, the client must staff that queue.
12. **How is a voice channel different from WhatsApp text?** Different
    failure surface: no transcript the DPO can search, harder consent and
    erasure, and discovery evidence cuts against it for this audience, so I
    kept it as a later option until text-funnel losses justify the build.
