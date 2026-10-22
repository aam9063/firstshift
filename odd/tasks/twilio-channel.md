# Feature: twilio-channel

## Header

- **Objective:** receive WhatsApp messages from the Twilio sandbox (subaccount) through a cloudflared tunnel, persist them as message.in, route them into the deterministic core, and reply through the outbox whatsapp port. Sandbox scope; hardening (templates, 24h window, receipts) stays in F12.
- **Status:** closed, smoke-tested through the tunnel; real sandbox message pending user credentials
- **Branch:** feature/agents-simulator (stacked, worktree backend-infra).
- **Trigger:** user request to raise the Twilio tunnel now, ahead of F12.

## Specs

- S1 (user, verbatim): "Levanta el tunel para twilio. Aunque mira estoy compartiendo twilio con otro proyecto mio y quiero tenerlos separados."
- S2 (user decision): Twilio separation via subaccount: subaccount SID + API Key SID/Secret in env (TWILIO_ACCOUNT_SID may be the subaccount SID); credits draw from the parent account.
- S3 (channel contract, design/integration-contracts.md §7): inbound WhatsApp message -> message.in event; outbound via MessagingChannelPort; idempotency on provider message id (Twilio MessageSid).
- S4 (G1/G2): first reply carries the AI disclosure; consent captured on first interaction (existing core path).
- S5 (security): validate X-Twilio-Signature with the subaccount auth token before processing; reject unsigned when TWILIO_VALIDATE_SIGNATURE=true.
- S6: candidate lookup by phone (From number); unmatched phone gets a polite holding reply and a logged unmatched_inbound event, never a new candidate (candidate creation stays behind the HireDesk webhook).

## Constraints

- Sandbox scope: no template messages, no media, no status callbacks in this feature (F12).
- Outbound replies go through the outbox (port whatsapp) and the relay/adapter delivers via Twilio REST using the subaccount credentials.
- Tests offline: respx mocks the Twilio REST API; signature validation tested with known vectors.
- No web/ changes.

## Tasks

| ID | Spec | Task | Status |
|---|---|---|---|
| T1 | S3,S5,S6 | POST /webhooks/whatsapp: signature validation, MessageSid dedup, phone lookup, message.in, dispatch | done (2cbb402 + 1a2ff20) |
| T2 | S2,S3 | TwilioChannelAdapter (REST send with subaccount creds) + relay wiring | done (2cbb402) |
| T3 | - | cloudflared tunnel running; env.example + README sandbox setup section | done: tunnel live, env.example updated; README section pending F12 |
| T4 | - | Close with live sandbox smoke test evidence | done: tunnel round-trip with signed request (unmatched path), replay dedup 200 replayed, invalid signature 403; real WhatsApp test pending user subaccount creds |

## Open questions

- None blocking. The user provides subaccount credentials in .env (never committed).

## Log

- L1 (user, verbatim): "Vamos a retomar. Levanta el tunel para twilio. Aunque mira estoy compartiendo twilio con otro proyecto mio y quiero tenerlos separados. Como puedo hacerlo? Puedo hacer otra api key dentro de la misma cuenta y usar los creditos de esa cuenta?"
- L2: Parent decision given to user: subaccount (not bare API key) for real separation; API Key inside the subaccount; credits draw from the parent balance; each subaccount has its own WhatsApp sandbox and join code.
- L3: Running stack observed: firstshift backend on host 8001 (container stale from F01; local uvicorn used for the tunnel until rebuilt), tri-coach on 8000 (other project), cloudflared 2026.9.3 available.
- L4: Smoke test evidence (through the live tunnel): signed request -> 200 unmatched_inbound; same MessageSid replayed -> 200 replayed; forged signature -> 403. Smoke found a real bug: dedup only checked message.in so unmatched-path replays duplicated events; fixed by deduping on both message.in and unmatched.inbound (1a2ff20) and promoting unmatched.inbound to EventType.
- L5: Remaining for the real sandbox: user creates the Twilio subaccount and fills .env (subaccount SID, API key SID/secret, auth token), joins the sandbox from their WhatsApp, points the sandbox webhook at the tunnel URL, and restarts the backend. Then a real WhatsApp message from a known candidate phone exercises the candidate path (D1-style).
