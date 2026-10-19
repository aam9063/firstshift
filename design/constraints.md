# Constraints: crew hiring pilot

- **Phase:** 2, problem framing (spec: `specs/02-problem-framing.md` section 5).
- **Rule:** every constraint is written as a testable rule the Phase 3 design must satisfy, with its source. Phase 3 and the build must reference these IDs.

## Legal and compliance (EU and Spain)

| ID | Testable rule | Source |
|---|---|---|
| C-L1 | Before any candidate data is processed, every candidate receives a transparent notice stating the lawful basis, and consent (where the basis is consent) is captured with a timestamp and the version of the notice shown. A test: for any candidate record, the notice version and consent timestamp can be retrieved. | [T-laura-18, T-laura-26] |
| C-L2 | Consent is per channel: the system never messages a candidate on WhatsApp who only consented to email. A test: attempting to send on a non-consented channel is blocked and logged. | [T-laura-26] |
| C-L3 | Data minimization: the system collects only the fields it can name a use for (contact, availability as concrete shifts, languages, documents required by Nómina360 registration). A test: the field list in the schema maps one to one to named uses, reviewed by the DPO. | Brief section 6 (GDPR compliance and auditability); [T-laura-18] |
| C-L4 | Rejected and stale candidate records are deleted or anonymized on a retention schedule that actually executes. A test: a record older than the configured retention is gone from every store, including backups strategy documentation, without manual intervention. | [T-laura-08, T-laura-18] (today HireDesk keeps records forever by default) |
| C-L5 | Right of access and erasure is fulfillable end to end: from one request, the system can list and delete or export every trace of a candidate, including conversation history. A test: a drill per pilot month produces a complete, verifiable record inventory. | [T-laura-12] ("no puedo borrar lo que no sé que existe"), [T-laura-22] |
| C-L6 | Every reject and every offer has a named human decision-maker on record with the date and the facts they saw. No decision that significantly affects a candidate is based solely on automated processing (GDPR article 22). A test: for 100% of sampled rejections and offers, the audit trail names the human reviewer; the agent's output is a recommendation only. | [T-jordi-22] ("el rechazo final siempre lo firme una persona"), [T-laura-18, T-laura-20] |
| C-L7 | Recruitment is designed as high-risk AI (EU AI Act Annex III): human oversight with authority to override, logging of agent recommendations and human decisions, explicit transparency to candidates that they are talking to an AI, documented data governance. Note: the application dates of the high-risk obligations have been under revision and must be checked against the state of the law at deployment time, not from this document. | Spec section 5; [T-laura-28] (DPIA and signature before a single candidate is contacted) |
| C-L8 | Food hygiene: Spanish law no longer requires a "carnet de manipulador", but the employer must ensure and be able to show food hygiene training. The LearnBite module is therefore a precondition to food-handling tasks on day 1, never a precondition to hiring or to an offer. A test: a hire without the module can be offered, registered and scheduled, but the system flags no food-contact tasks until completion is confirmed. | Spec section 5; [T-iker-06] (no module, "ni un pan" of food contact) |
| C-L9 | Contracts and Social Security registration stay with People Ops in Nómina360: FirstShift prepares and validates the data and never signs or registers. A test: the Nómina360 write path is limited to validated employee-creation payloads routed through People Ops' flow; there is no contract-signing or alta-registration capability. | [T-sofia-04, T-sofia-18]; brief section 3 |

## Operational

| ID | Testable rule | Source |
|---|---|---|
| C-O1 | No new app or dashboard for managers or crew: anything a manager must do reaches them as a WhatsApp message with quick-reply buttons, completable in one tap per decision. A test: every manager action in the happy path is a WhatsApp quick reply or a plain reply; no login, portal or password exists for managers. | Brief section 6; [T-raul-26]; [T-yolanda-26] |
| C-O2 | Quick replies are the standard interaction: every message that asks a manager for a decision offers at most two or three buttons plus free text. A test: the message catalog review shows no manager prompt requiring navigation or multiple screens. | Spec section 5; [T-candidate-b-22] (concrete asks get answered) |
| C-O3 | Multi-tenant ready: data is partitioned by brand and by restaurant from day one, so a franchisee can be onboarded later without code changes. A test: every record carries brand and restaurant scope and no query crosses scope without an explicit, logged filter. | Spec section 5; brief section 1 (18% franchised) |
| C-O4 | Spanish first: all candidate and manager conversations work in Spanish from day one; Portuguese and English are supported for candidates where the spec requires, selected explicitly, never guessed from names. A test: the message catalog is reviewed per language; the language choice is a stated preference on the profile. | Spec section 5; brief section 1 (30% non-Spanish nationals in coastal units); [T-candidate-c-22] |

## Technical

| ID | Testable rule | Source |
|---|---|---|
| C-T1 | Only documented APIs are used: HireDesk REST and webhooks, Nómina360 employee-creation REST, ShiftGrid REST, LearnBite enrollment API and completion webhooks, TillCloud read-only sales API, Graph API. No direct database access, ever. A test: the network and code review finds no connection path outside the documented API list. | Brief section 6; [T-hugo-22, T-hugo-28] |
| C-T2 | Nómina360 client respects the rate limit of 60 requests per minute with backoff, and its throttling behavior is treated as undocumented: the client must handle responses that do not match the documentation. | [T-hugo-14] ("it is not a suggestion") |
| C-T3 | Every Nómina360 response is validated by body, never by status code alone, because validation failures return HTTP 200 with an error body. A test: an injected error-body-200 fixture is detected and retried or alerted, never recorded as success. | [T-hugo-16, T-hugo-20] (the July incident) |
| C-T4 | Nómina360 state is verified through the nightly CSV export, which is the reliable read: a write is not counted as confirmed until the next CSV shows it. A test: the reconciliation job flags any write that is API-"confirmed" but absent from the CSV. | [T-hugo-18] ("what is in the file is what is actually in the system") |
| C-T5 | Every write to a client system is idempotent under a key IT controls: the same onboarding arriving twice updates or no-ops and never duplicates. A test: replaying any write with the same key produces one record. | [T-hugo-22, T-hugo-24] |
| C-T6 | Every write is logged with what, when and by whom, queryable by the idempotency key end to end for a single person. A test: from one idempotency key, IT can retrieve the full write history in one query. | [T-hugo-22, T-hugo-24, T-hugo-30] |
| C-T7 | Every write is reversible or compensable: for each write type, the design names the compensating action (correction record, cancellation flow, or manual procedure owned by People Ops) before go-live. A test: the runbook lists a compensating action per write type, reviewed by IT and People Ops. | Spec section 5; [T-hugo-20] (rebuilding records by hand) |
| C-T8 | EU data residency for data at rest, including candidate documents and conversation history; subprocessors are named and EU-hosted. A test: infrastructure review confirms at-rest storage regions; the subprocessor list is a signed artifact for the DPO. | [T-hugo-22, T-hugo-28]; [T-laura-22] |

## Cross-cutting process gate

| ID | Testable rule | Source |
|---|---|---|
| C-X1 | No candidate is contacted before the DPIA is signed by the DPO and IT has approved the write paths. A test: the signed DPIA and IT design review are dated before the first outbound message. | [T-laura-28]; [T-marta-22] |
