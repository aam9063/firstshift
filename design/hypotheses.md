# Hypotheses: crew hiring pilot

- **Phase:** 2, problem framing (spec: `specs/02-problem-framing.md` section 4).
- **Rule:** each hypothesis is falsifiable, names the metric that tests it and the kill threshold that makes us drop the associated design. Numbers are adjusted to what discovery found (`discovery/funnel-baseline.md`, `specs/00-client-brief.md` section 4, transcripts `[T-name-NN]`); the spec's expected shape was a guide and the evidence wins. Where discovery found no number, the hypothesis says so and the pilot instruments it.

## H1: Fast first contact on WhatsApp converts the silent queue

**Hypothesis:** Contacting every applicant on WhatsApp within 1 hour of application (median) raises the interview show rate from 62.0% to 80% or more, and lifts the contacted rate from 59.0% to 95% or more.

**Why these numbers:** the spec's draft said 5 minutes; the evidence anchor is a real reply under 1 hour that won the candidate over six silent chains [T-candidate-a-10, T-candidate-a-12], and candidates answer messages that name the restaurant and ask one concrete question [T-candidate-b-22]. The show-rate lever is also the shift away from unknown-number phone calls, which about half of candidates will not answer [T-jordi-14].

**Testing metrics:** contacted rate (baseline 59.0%), interview show rate (baseline 62.0%), time to first contact (baseline 3.9 days median).

**Kill threshold:** after 4 weeks at full application volume in at least 9 of 12 pilot units, if show rate is below 70% or the median first contact exceeds 24 hours, we drop the speed-first design and re-examine the message content instead.

## H2: Concrete shift questions replace the availability dropdown

**Hypothesis:** Collecting availability as concrete shifts ("can you do Saturday close?") instead of a form dropdown, and carrying it as structured data into ShiftGrid, raises offer acceptance and 30-day retention of pilot hires versus the control group.

**Why:** the dropdown is a dead field that rejects the best weekend-shift profiles: a candidate rejected twice for "availability" without anyone ever asking which shifts [T-candidate-b-08 to T-candidate-b-10], a student who answered "completa" because she did not understand it [T-candidate-a-20], and a churned hire whose stated availability never reached the rota [T-churned-14]. No baseline number for offer acceptance exists (the funnel conflates it with document collection), so this hypothesis is tested comparatively against control.

**Testing metrics:** offer acceptance within 7 days, 30-day retention (baseline 72.0%), share of pilot hires whose rota matches collected shift availability.

**Kill threshold:** by day 90, if 30-day retention of hires with concrete availability is not at least 5 percentage points above the control group, we drop the claim that shift-level availability improves retention and keep it only as data hygiene.

## H3: Pre-collecting documents and the hygiene module cuts offer-to-rota time

**Hypothesis:** For candidates who opt in, starting document collection (the three chronically late ones: bank certificate, social security number, food hygiene certificate [T-sofia-10]) and the LearnBite food hygiene module **before** the interview cuts the offer-to-first-shift time from 9 days to 3 days or less, and the offer-to-on-rota time from about 7.5 days (sum of funnel medians) to 3 days or less.

**Why:** the window is the largest time sink in the funnel (5.1 median days documents to on rota) and is gated by Nómina360 creation, which takes 3 to 6 days [T-yolanda-20], plus a rota that locks Thursdays [T-hugo-12]. A hygiene certificate alone once cost a 5-day start delay [T-sofia-14]. Only opt-in candidates: consent is explicit per channel with timestamp and notice version [T-laura-26].

**Testing metrics:** median offer to first worked shift (baseline 9 days, brief §4; 9.5 funnel), median documents-complete-to-on-rota (baseline 5.1 days), share of day-1 starts with the hygiene module done (today 2 of the trainer's last 5 arrived without having started it [T-iker-08]).

**Kill threshold:** after 6 weeks, if median offer-to-first-shift is still above 6 days, we drop pre-collection as the mechanism and escalate the Nómina360 creation lead time to IT as the binding constraint.

## H4: Day-before confirmation plus a named backup cuts day-1 no-shows

**Hypothesis:** A day-before WhatsApp confirmation of the first shift, plus a named backup candidate per open shift, cuts day-1 no-shows from 18% to under 8%.

**Why:** the baseline no-show sits inside the waiting window (day-1 no-show 17.9% funnel; 18% brief §4), and the candidate often learns the shift the night before, at 22:30 in one documented case, or by chance from a crew group [T-churned-08, T-candidate-a-16, T-candidate-a-18].

**Testing metrics:** day-1 no-show rate (baseline 17.9%), share of first shifts confirmed to the candidate at least 24 hours ahead, share of open peak shifts with a named backup.

**Kill threshold:** after at least 100 pilot hires, if the no-show rate is above 12%, we drop the backup mechanism as ineffective and test the confirmation alone before spending more on it.

## H5: Managers approve offers from a single WhatsApp message in under 2 hours

**Hypothesis:** When the offer request is one WhatsApp message with a candidate summary and two quick-reply buttons, the median manager approval time is under 2 hours.

**Why:** managers already run hiring from personal WhatsApp [T-yolanda-14, T-yolanda-16] and reject any new portal [T-raul-26]; the single-message pattern matches how candidates say they answer [T-candidate-b-22]. **No baseline exists for approval latency**: today the approval is a conversation and never recorded (`discovery/systems-and-data.md`, data object table). The pilot instruments it; the threshold is a design commitment, not an evidence-derived number.

**Testing metrics:** median time from approval request to manager reply; adoption (share of offers routed through the WhatsApp request rather than side conversations).

**Kill threshold:** after 50 approval requests, if the median is above 8 hours or adoption is below 60% of offers, we drop the in-WhatsApp approval flow and route approvals through the manager's existing side chats with logging, or revisit the request format.

## H6: Day-3 and day-10 check-ins catch rota and expectation mismatch

**Hypothesis:** A day-3 WhatsApp check-in that reads back the promised schedule against the real rota, plus a day-10 check-in, saves a measurable share of week-1 quits by surfacing mismatch while it is fixable.

**Why:** 2 of the trainer's last 5 hires quit in week 1 with the same words, "this is not what I was told" [T-iker-14 to T-iker-16]; the churned hire quit after an unanswered swap request and a night-before rota, and says a day-1 intervention would have kept her [T-churned-10, T-churned-18, T-churned-22 to T-churned-24]. Overall, 28.0% of day-1 workers are gone by day 30 (funnel). Week-1 quits are not separately measured today, so the pilot instruments the split.

**Testing metrics:** 30-day retention of pilot hires (baseline 72.0%), share of check-ins that surface a schedule or expectation conflict, share of surfaced conflicts resolved within 48 hours, week-1 quit rate (instrumented from zero).

**Kill threshold:** by day 90, if 30-day retention of the check-in cohort is not above the control group, we drop the check-ins as a retention lever and keep only the conflict log for exit analysis.

## H7: One language question unlocks the tourist-drive-thru profile

**Hypothesis:** Asking about languages in the first conversation, storing it as a tagged fact on the profile, and surfacing it during screening increases the share of multilingual candidates reaching interview at tourist-facing drive-thru pilot units, versus the funnel's current contacted-to-interview behavior.

**Why:** two years of applications, zero language questions, in a town where half the drive-thru cars are foreign [T-candidate-c-08, T-candidate-c-10], while the trainer calls customer-facing ability "gold here with the tourists" [T-iker-18]. **No baseline exists**: language was never collected, so the pilot instruments the tag and compares interview-advancement rates between tagged-multilingual and other candidates within the pilot.

**Testing metrics:** share of interviews at drive-thru pilot units with at least one tagged non-Spanish language; interview-advancement rate of tagged candidates versus untagged.

**Kill threshold:** by day 90, if tagged multilingual candidates are not interviewed at a higher rate than comparable untagged candidates, or if managers never use the tag, we drop it as a screening input and keep it as rota-planning data only.
