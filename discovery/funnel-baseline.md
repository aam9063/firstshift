# Funnel baseline: crew hiring, seeded mock dataset

- **Source:** output of `uv run python -m mocks.funnel` (re-runnable, seeded, reproducible from `mocks/seed/`).
- **Dataset:** 4,500 applications across 15 restaurants (12 pilot + 3 control), last 6 months, fixed seed 42.
- **Scope:** this file reports the script output. Interpretation and cost estimates live in `discovery/pain-points.md`; design implications in `discovery/insights.md`.

## The funnel

Counts, conversion per stage and median elapsed days between stages, exactly as printed by the script (the "Median days" of a stage is the median time from the previous stage to that stage; the "Absolute loss" column is derived arithmetic between consecutive counts):

| Stage | Count | Conversion | Median days | Absolute loss vs previous stage |
|---|---|---|---|---|
| applied | 4500 | - | - | - |
| contacted | 2655 | 59.0% | 3.9 | -1845 |
| screened | 1991 | 75.0% | 2.0 | -664 |
| interview_scheduled | 1394 | 70.0% | 4.3 | -597 |
| interview_attended | 864 | 62.0% | 5.0 | -530 |
| offer | 518 | 60.0% | 3.1 | -346 |
| documents_complete | 440 | 84.9% | 2.4 | -78 |
| on_rota | 396 | 90.0% | 5.1 | -44 |
| day1_worked | 325 | 82.1% | 1.5 | -71 |
| day30_active | 234 | 72.0% | n/a | -91 |
| day90_active | 156 | 66.7% | n/a | -78 |

Overall: 325 of 4,500 applications (7.2%) reach a first worked shift. Summing the stage medians gives a median of roughly 27.3 days from application to first worked shift (approximation: sum of per-stage medians, not a per-candidate measurement).

## Largest absolute loss of candidates

**The first contact step: -1,845 candidates**, 41.0% of everyone who applied was never contacted. No other stage loses even a third of that (the next largest is -664 at screening). The front door is where the funnel empties, and the loss is silent: these candidates get no rejection, no reply, nothing, which matches what candidates reported in the interviews (`discovery/transcripts/candidate-a.md`, five of six chains never answered; [T-jordi-14], the head of TA knows this by complaints, not reports).

## Largest time sink

**The hired-to-rota window: 5.1 median days** between documents complete and on rota, the largest stage median in the funnel. This is precisely the gap `discovery/systems-and-data.md` identifies as unowned: document chasing plus employee creation in Nómina360, which takes 3 to 6 days and gates scheduling ([T-yolanda-20], [T-sofia-18]). The runner-up is the 5.0 median days between interview scheduling and attendance, the window where the 38.0% interview no-show happens. The two biggest time sinks and the two behavioral drop-offs (41.0% never contacted, 38.0% no-show) sit at these same two stages.

## Baseline metrics vs the client brief

Comparison against `specs/00-client-brief.md` section 4 (tolerance per the feature document: conversions within 5 percentage points, medians within 1.0 day):

| Metric | Seeded funnel (seed 42) | Brief baseline | Delta |
|---|---|---|---|
| Applicants never contacted | 41.0% | 41% | 0.0 pp |
| Median days to first contact | 3.9 | 3.8 | +0.1 days |
| Interview no-show rate | 38.0% | 38% | 0.0 pp |
| Median days, verbal offer to first worked shift | 9.5 | 9 | +0.5 days |
| Day-1 no-show (hired, never shows up) | 17.9% | 18% | -0.1 pp |
| 90-day attrition of new hires | 52.0% | 52% | 0.0 pp |

Every metric is inside the stated tolerance, so the seeded dataset is consistent with the baseline the client reported.

## Dataset shape and caveats

- Seeded and reproducible: seed 42, files under `mocks/seed/`, re-run with `uv run python -m mocks.funnel`.
- 4,500 applications, 15 restaurants, last 6 months.
- **Full-maturation caveat for late stages:** the dataset models every application as if its cohort had already matured to day 90. Real recent cohorts would not yet show their final day-30 and day-90 actives, so the late-stage counts and conversions (day30_active 234, day90_active 156, and the 52.0% attrition they imply) should be read as steady-state values, slightly optimistic for the most recent months.
- Median elapsed days are not modeled for the post-hire stages (day30, day90 show n/a), so the 27.3-day pipeline figure covers application to first worked shift only.
- The dataset models only the official funnel. Shadow-path hires (the managers' "maybes" pool, logged late or never, [T-yolanda-14], [T-yolanda-18], [T-jordi-20]) are outside it, so real hiring volume per restaurant is higher than these counts suggest. That volume stays qualitative, per the feature document's open questions.
