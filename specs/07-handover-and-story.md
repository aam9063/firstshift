# 07 · Handover and story: make the work transferable and tellable

**Goal:** leave the client (and a future engineer) able to run and extend FirstShift without the author, and turn the project into a clear, honest story for an FDE interview.

**Outputs:** `docs/handover.md`, `docs/case-study.md`, `docs/demo-video-notes.md`, `docs/interview-narrative.md`, updated `README.md`.

---

## 1. Handover pack

`docs/handover.md`:
- What exists, what is stubbed, what is simulated (one table, no ambiguity).
- How to run, test, evaluate and deploy, in 10 commands or fewer.
- Architecture in one diagram plus links to the ADRs.
- Open risks and known limitations, ranked.
- Next 3 recommended features with expected impact: demand-triggered requisitions (option 3), crew referral loop (option 9), voice screening (option 10).
- Ownership after handover: who on the client side owns prompts, criteria, the bench, the DPIA.

## 2. Case study (for the portfolio and the README)

`docs/case-study.md`, about 800 words, structure:
1. **Context:** a fictional Iberian QSR group, summer hiring pressure, numbers from the brief.
2. **What I found:** the 3 strongest discovery insights, each with one piece of evidence.
3. **The reframe:** from "screen faster" to "time to first productive shift".
4. **What I built:** concept in one sentence, architecture diagram, the 3 agents, the deterministic core.
5. **How I knew it worked:** eval and simulated-pilot results with before/after numbers and the iteration log highlights. Clearly labeled as simulation.
6. **What I would do with a real client next:** shadow wave, sandbox credentials, DPIA, champion.
7. **How I worked:** agent-first development with ODD in gentle-shell: specs as source of truth, one feature document per substantial change, test-first core, evidence-based checkoffs. Show one real `odd/tasks/*.md` excerpt.

## 3. Demo video (2 minutes)

`docs/demo-video-notes.md`: shot list based on `docs/demo-script.md` (D1, D4, D6), English voice-over, captions, final frame with the 3 headline numbers and the repo link. Record with the simulator at fast-forward.

## 4. Interview narrative (English)

`docs/interview-narrative.md`, written to be spoken, not read:

- **30-second version:** "I simulated a full FDE engagement for a fast-food chain..." ending with the north star result.
- **2-minute version** in STAR form: Situation (client and trigger), Task (pilot charter), Action (discovery insight, reframe, design choices, iteration with evals), Result (numbers, labeled as simulated) plus one thing I would do differently.
- **Bridge to real experience:** connect to the author's real work: owning the full lifecycle of an internal tool for an industrial client at his consultancy, from spike to production, with direct client contact and CI/CD on Azure DevOps. Use the same discovery-to-delivery arc. Do not invent details beyond what the author confirms.
- **Likely questions and crisp answers** (at least 10), for example:
  - How did you decide what to build first?
  - How do you keep an LLM from making hiring decisions?
  - What happens when the client's HRIS has no webhooks?
  - How would you get a skeptical restaurant manager to use it?
  - How do you know the agents are not biased?
  - What would you measure in the first week of a real pilot?
  - What did you get wrong, and how did evals show it?
  - How do you work with AI coding agents without losing control of quality?
  - Why WhatsApp and not an app?
  - What is different about deploying for a franchisee vs company-operated units?

## 5. Relevance to the target company (public facts only)

The narrative may reference only these publicly reported facts about the target company and must not claim inside knowledge:
- It builds AI agents for frontline workforce management, with named agents covering recruiting, onboarding and engagement and retention.
- Its agents reach workers through WhatsApp, SMS and voice, because frontline workers often have no corporate email.
- Public reporting lists large restaurant and retail groups among its customers, including operators of major fast-food brands, and the company raised a Series A in June 2026.

Frame FirstShift as "how I would think about a deployment like the ones you run", never as a replacement for or a critique of their product. Highlight the FDE-specific skills shown: discovery with non-technical stakeholders, reframing the ask, integrating into messy systems, measuring outcomes, and changing human workflows.

## Exit criteria

- [ ] Handover doc lets a new engineer run evals within 15 minutes.
- [ ] Case study under 900 words with real (simulated) numbers and caveats.
- [ ] Demo video recorded, under 2:15.
- [ ] Narrative rehearsed out loud twice; 10+ Q&A prepared.
