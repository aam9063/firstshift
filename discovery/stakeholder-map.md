# Stakeholder map: Lumbre Burger Group crew hiring pilot

Evidence-based stakeholder map for the 90-day Costa Blanca pilot. Sources of truth: `specs/00-client-brief.md` sections 1 and 7 and the twelve simulated interviews in `discovery/transcripts/`. Every claim about the client cites a transcript line ID (for example [T-jordi-08]) or a brief section. All quotes are verbatim from the transcripts.

## 1. Power/interest grid

Power = ability to stop or force the pilot. Interest = how directly hiring speed and quality touch their daily work.

| | Low interest | High interest |
|---|---|---|
| **High power** | IT (Hugo): enables or blocks integration [T-hugo-22, T-hugo-28] | CPO (Marta): economic buyer, owns go/no-go [T-marta-22] · Area Ops Director (Raúl): owns the pilot's 42 restaurants and March hiring wave [T-raul-02, T-raul-28] |
| **Low power** | CFO / board (inform via Marta; the board ask is undefined: "IA en RRHH para el primer trimestre" [T-marta-04]) | Restaurant managers (Yolanda): adoption decides everything ("Si Yolanda no lo usa en Benidorm, esto está muerto" [T-marta-22]) · Crew trainers (Iker) · People Ops / Payroll (Sofía) · TA team (Jordi) · DPO (Laura): low formal power, absolute veto on data [T-laura-28] · Candidate cohort |

Notes on placement:

- Laura sits low on formal power but her veto is absolute: "Any new processing in hiring needs a DPIA and my signature before a single candidate touches it, not after the pilot" [T-laura-28]. In practice she belongs on the high-power row through her veto right, which Marta confirms: "Laura, la delegada de protección de datos, tiene que decir sí sin pelos en la lengua" [T-marta-22].
- Hugo is the same shape: low interest in the hiring outcome, high blocking power over any write into Nómina360 [T-hugo-22, T-hugo-28], again confirmed by Marta [T-marta-22].
- The candidate cohort has no organizational power but the highest interest: they apply to six chains in one evening and take the first that answers [T-candidate-a-06, T-candidate-a-10].

Mermaid quadrant equivalent:

```mermaid
quadrantChart
    title LBG pilot: power vs interest
    x-axis Low interest --> High interest
    y-axis Low power --> High power
    quadrant-1 Manage closely
    quadrant-2 Keep satisfied
    quadrant-3 Monitor
    quadrant-4 Engage and convince
    Marta (CPO): [0.7, 0.95]
    Raul (Area Ops): [0.85, 0.9]
    Hugo (IT): [0.25, 0.85]
    Laura (DPO): [0.4, 0.85]
    Yolanda (Managers): [0.95, 0.55]
    Jordi (TA): [0.8, 0.5]
    Sofia (People Ops): [0.75, 0.45]
    Iker (Trainer): [0.85, 0.3]
    Candidate cohort: [0.95, 0.2]
    Board/CFO: [0.2, 0.75]
```

## 2. Per-stakeholder detail

### Marta Ibáñez, Chief People Officer (economic buyer)

- **Decision right: approve.** "Yo doy el visto bueno de negocio, pero no me pidas que apruebe yo sola" [T-marta-22]. She names Laura, Hugo and the managers as co-conditions.
- **Win in her own words:** "Que la contratación de verano no se me caiga otra vez en julio. Que las gerentes me digan que dedican menos tiempo a papeleo. Y que el consejo vea algo más que diapositivas: números de las doce tiendas piloto" [T-marta-14].
- **Evidence she needs:** real numbers from the 12 pilot restaurants, not slides [T-marta-14]; reassurance against the employer-brand nightmare of a rude bot screenshot going public [T-marta-18, T-marta-20]; progress on the labour-inspection documentation findings [T-marta-26].
- **Channel and cadence:** direct and short. She opened with "tengo treinta minutos, no cuarenta y cinco" [T-marta-02] and Raúl confirms she is reachable on WhatsApp [T-marta-24]. Monthly written summary to her plus the board-facing pilot numbers; no long meetings.

### Raúl Sempere, Area Operations Director, Costa Blanca (day-to-day champion, hypothesis to test)

- **Decision right: influence (close to veto over adoption).** The coast is his: "La costa es suyo. Si le digo 'esto te va a dar gente para el sábado', me escucha. Si le digo 'es un proyecto de RRHH', ni me contesta el WhatsApp" [T-marta-24]. His stated kill condition: "Si me dices 'la gerente tendrá que entrar cada mañana en un portal nuevo', ya me has perdido" [T-raul-26].
- **Champion hypothesis test:** the spec hypothesizes Raúl as the day-to-day champion. His transcript supports it conditionally. He commits publicly if speed improves: "Que el hueco de agosto se cubra en días, no en semanas... Si eso ocurre, yo soy el primero defendiéndolo en la reunión de dirección" [T-raul-24]. But he will not champion information dashboards: "esto no es un problema de información, es un problema de que la gente no llega" [T-raul-20]. Verdict: yes as champion, but only if the pitch is Saturday coverage, not HR tooling, and only with a March hiring plan ("Ese mes lo decide todo" [T-raul-28]).
- **Win in his own words:** "Yo necesito gente el sábado, no informes el lunes" [T-raul-02].
- **Evidence he needs:** candidates saying yes to a manager reaching the rota in days, not weeks [T-raul-24]; no new portal or password for managers [T-raul-26]; a March summer-hiring plan he can commit operations to [T-raul-28].
- **Channel and cadence:** phone calls. He runs his area by calls, not screens: "La cobertura real la sé yo por las llamadas, no por la pantalla" [T-raul-18]. Weekly call during the pilot, WhatsApp for short items.

### Yolanda Ferrer, Restaurant Manager, Benidorm Playa (end user whose behavior must change)

- **Decision right: adoption veto in practice.** "Si un candidato se siente tratado como un número..." is Marta's fear, but the adoption lever is Yolanda's [T-marta-22]. Her own stop condition: "If a tool puts a stranger between me and the twenty-five names I already trust, I will use it once and never open it again" [T-yolanda-26].
- **Win in her own words:** "Si sobrevivimos al verano, sobrevivimos a todo" [T-yolanda-28]; closer to daily life, a hire who "said yes to my face" reaching the rota without the 11-day paper gap [T-yolanda-10, T-yolanda-12].
- **Evidence she needs:** the tool must keep her "maybes" list working, not replace it [T-yolanda-14, T-yolanda-16]; hires must reach Nómina360 faster than the current 3 to 6 days [T-yolanda-20]; it must not cost her time on the floor [T-yolanda-24, T-yolanda-26].
- **Channel and cadence:** WhatsApp, informal. She already runs hiring from her personal WhatsApp [T-yolanda-14] and rejects anything that pulls her off the floor [T-yolanda-24]. Reach her inside the shift pattern; short messages, not meetings.

### Iker Lozano, Crew Trainer, Benidorm Playa (end user, receiving side)

- **Decision right: inform, plus daily-life influence.** Nobody consults him today: "A mí nadie me llama. Nadie me dice: Iker, el lunes entra uno, tal y cual" [T-iker-20].
- **Win in his own words:** "Module done before they walk in, rota known by them and by me, and them knowing what the job actually is. With those three, I can make anyone useful in a week" [T-iker-22].
- **Evidence he needs:** hygiene module completed before day 1 (currently 2 of his last 5 arrived without it [T-iker-08]); advance notice of who arrives and when [T-iker-20]; fewer week-1 quits caused by expectation mismatch [T-iker-16].
- **Channel and cadence:** in-person, crew room, before or after shifts (the interview itself was scheduled that way). A pre-shift notification of incoming hires; he has no dashboard appetite.

### Jordi Puig, Head of Talent Acquisition (influence, process owner)

- **Decision right: influence, with veto language on black boxes.** "Si lo que me ofrecen es una caja negra que rechaza gente sin que nadie la lea, eso es un no" [T-jordi-22].
- **Win in his own words:** "Si me hablas de que la pila se ordene sola, de que nadie bueno se pierda en una cola, y de que la decisión final la siga tomando una persona, eso no es perder control, es respirar" [T-jordi-22].
- **Evidence he needs:** a live comparison on real volume, proposed by him: "Que me enseñen lo que haría con cien candidaturas de Benidorm en julio, y que yo, con mi equipo, compare" [T-jordi-24]; the final rejection always signed by a human [T-jordi-22, T-jordi-24]; HireDesk data he can trust (today he calls his own reports "basura" [T-jordi-16]).
- **Channel and cadence:** existing monthly ops rhythm. He reviews the HireDesk report in a monthly meeting [T-jordi-16]. Work through his team in the ATS itself, not a parallel inbox.

### Hugo Andrade, Integration Lead, IT (technical gatekeeper)

- **Decision right: veto on integration design.** "If I cannot see in a log exactly what was written, when, and by whom, the answer is no" [T-hugo-22]. Marta confirms: "Hugo, de IT, tiene que aguantar la integración" [T-marta-22].
- **Win in his own words:** "So whatever comes next, I want monitoring and alerts on those writes, not a phone call from payroll on payday" [T-hugo-30].
- **Evidence he needs:** documented APIs only, no direct database access, EU data residency [T-hugo-22, T-hugo-28]; idempotent writes with a queryable key and end-to-end audit [T-hugo-22, T-hugo-24]; safe handling of the Nómina360 traps (60 requests per minute, HTTP 200 with error body, nightly CSV as the reliable read [T-hugo-14 to T-hugo-18, T-hugo-20]); no new app for crew or managers [T-hugo-28].
- **Channel and cadence:** written technical specs and logs, async. He cares about not being the 3 a.m. call [T-hugo-30]. Design review before any write path goes live, then monitoring reports.

### Laura Cebrián, Data Protection Officer (compliance gatekeeper)

- **Decision right: veto.** DPIA and her signature before a single candidate touches the system [T-laura-28]; Marta requires her unconditional yes [T-marta-22].
- **Win in her own words:** "No automated decisions about people. Assist, yes. Decide, no. Show me the logs and I can sleep" [T-laura-18].
- **Evidence she needs:** lawful basis and versioned consent per candidate, retention rules that execute, a full audit trail, human review before any exclusion [T-laura-18, T-laura-20]; EU-only data, named subprocessors, end-to-end deletion [T-laura-22]; explicit per-channel consent for WhatsApp messaging [T-laura-26].
- **Channel and cadence:** formal, written. DPIA submission and documentation review before the pilot starts [T-laura-28]. She also flags a counterintuitive opportunity: a governed messaging channel is a compliance improvement over personal WhatsApp, not a new risk [T-laura-24].

### Sofía Marques, People Ops and Payroll lead (influence, operational dependency)

- **Decision right: influence.** Nothing starts without her registration: "Without those I cannot create the employee in Nómina360, and without Nómina360 there is no payroll, no alta en la Seguridad Social, nothing" [T-sofia-04].
- **Win in her own words:** "If the documents arrived complete, checked, and in one place, with me knowing what is missing the same day it is missing, my team could go from chasing to registering" [T-sofia-26].
- **Evidence she needs:** the three chronically late documents (bank certificate, social security number, food hygiene certificate) collected and validated earlier [T-sofia-10, T-sofia-30]; no extra steps for her team [T-sofia-28]; no unregistered people working shifts [T-sofia-20].
- **Channel and cadence:** email and structured document intake, not new meetings. Today the chase runs on template emails and calls through managers [T-sofia-16]. Weekly status during summer waves.

### Candidate cohort (applicants, treated as one stakeholder)

- **Decision right: influence through behavior.** They choose with their feet: six applications in one evening, the first chain to answer wins [T-candidate-a-06, T-candidate-a-10].
- **Win in their own words:** "si alguien te contesta en una hora ya has ganado" [T-candidate-a-26]; "A quick no is better than a slow maybe" [T-candidate-b-18]; "if they want me for the summer, ask me in February, not in May" [T-candidate-c-14].
- **Evidence they need (what makes the process acceptable):** a fast, concrete first message naming the restaurant [T-candidate-b-22, T-candidate-c-22]; real questions about availability and languages instead of dropdowns [T-candidate-b-10, T-candidate-c-08]; early salary information [T-candidate-b-20, T-candidate-a-26]; a first shift communicated in advance, not the night before [T-churned-08, T-churned-24].
- **Channel and cadence:** WhatsApp, immediate. Speed is the deciding variable [T-candidate-a-10, T-candidate-a-12]; slow processes lose them [T-candidate-c-12].

### Board / executive committee (monitor)

- **Decision right:** ultimate budget authority through Marta; the ask is real but undefined ("IA en RRHH para el primer trimestre" [T-marta-04]) and was triggered by the eleven drive-thru closures reaching the board [T-marta-06].
- **Win in their own words:** the CEO wants "una respuesta creíble antes de la campaña de verano" [T-marta-04].
- **Evidence they need:** the pilot numbers from the 12 stores Marta will present [T-marta-14].
- **Channel and cadence:** quarterly board cycle via Marta; end of Q1 matters [T-marta-02 context note].

## 3. Required identifications

- **Economic buyer:** Marta Ibáñez, CPO. The brief names the CPO as buyer (brief section 6); her transcript confirms she owns the business sign-off [T-marta-22].
- **Day-to-day champion to recruit:** Raúl Sempere (hypothesis). Test result: supported conditionally. He publicly commits only if the pilot delivers speed for Saturdays and March [T-raul-24] and refuses any manager portal [T-raul-26]. Frame everything as operations, never as an HR project [T-marta-24].
- **Technical gatekeeper:** Hugo Andrade. Veto over integration design; idempotent, logged writes; Nómina360 fragility is the core technical risk [T-hugo-22, T-hugo-14 to T-hugo-20].
- **Compliance gatekeeper:** Laura Cebrián. DPIA and signature before any candidate contact [T-laura-28]; no automated decisions, full audit trail [T-laura-18, T-laura-20].
- **End users whose behavior must change:** Yolanda (managers generally) and, on the receiving side, Iker. Yolanda currently hires from a personal WhatsApp "maybes" list before any requisition exists and logs into HireDesk late, if at all [T-yolanda-14, T-yolanda-16, T-yolanda-18]. Any pilot that does not absorb that workflow will be bypassed [T-yolanda-26]. Iker needs the module done and advance notice or day 1 fails on his side [T-iker-06, T-iker-22].

## 4. Three stakeholders most able to block the pilot

1. **Laura Cebrián (DPO).** Hard gate: "Any new processing in hiring needs a DPIA and my signature before a single candidate touches it, not after the pilot" [T-laura-28], and Marta requires her "sí sin pelos en la lengua" [T-marta-22]. Her red lines are concrete and non-negotiable: no automated decisions, deletable end to end, EU data, named subprocessors, per-channel consent [T-laura-18, T-laura-20, T-laura-22, T-laura-26].
2. **Hugo Andrade (IT Integration Lead).** Controls the only paths into Nómina360, the system that gates everything (no registration, no rota [T-yolanda-20, T-sofia-04]). His requirements are unforgiving: 60 requests per minute, HTTP 200 with buried error bodies, idempotent logged writes or "the answer is no" [T-hugo-14 to T-hugo-22]. A silent failed write is a payroll incident he has already lived through [T-hugo-20].
3. **Yolanda Ferrer (and managers like her).** Adoption is the pilot's success criterion and it lives or dies at restaurant level: "Si Yolanda no lo usa en Benidorm, esto está muerto" [T-marta-22]. Managers already have a working shadow process (the maybes list) [T-yolanda-14, T-yolanda-16] and a stated one-use abandonment rule [T-yolanda-26]. Raúl generalizes the risk: one more portal and he is lost [T-raul-26].

Honorable mention: Raúl could block the March scale-up decision, which is where "se decide de verdad" [T-marta-26, T-raul-28], but as Area Ops Director for the pilot area he is more powerful as a champion than as a blocker.
