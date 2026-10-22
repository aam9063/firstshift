# Judge calibration report v1

- **Judge:** live, OpenAI `gpt-4.1-mini`, rubric version `v1` (clarity, warmth, brevity, language, honesty).
- **Labels:** 15 conversations x 5 criteria, hand-labeled by the project owner (genuine human labels, worksheet `evals/reports/calibration-v1.md`).
- **Run:** `uv run python -m evals.judge.calibration score --judge live --report evals/reports/eval-v1.json`.

## Agreement

75 scored cells. **Exact agreement 17%, within-1 agreement 48%.**

| criterion | n | exact | within 1 |
| --- | --- | --- | --- |
| clarity | 15 | 0% | 7% |
| warmth | 15 | 7% | 47% |
| brevity | 15 | 20% | 60% |
| language | 15 | 0% | 27% |
| honesty | 15 | 60% | 100% |

## Diagnosis: the disagreement is a scale mismatch on three criteria, not noise

Per-conversation pairs (human/judge) show a systematic direction:

- clarity: human 4-5, judge 2-3 (judge 2 points lower)
- warmth: human 3-5, judge 2-3 (judge 1-2 points lower)
- language: human 4-5, judge 2-3 (judge 1-3 points lower)
- brevity: mixed (judge sometimes higher)
- honesty: aligned (60% exact, 100% within 1)

## Inspection: the judge is defensible on the cases inspected

1. `eval-p002` (Portuguese candidate): the agent opens in Spanish, switches to Portuguese, then sends "Oferta de empleo de Lumbre Burger: responde SI para aceptar" in Spanish again. Human language score 5, judge 2. The judge is right: language drifts mid-conversation, which anchor 2 describes explicitly.
2. The same conversation ends with the raw internal token `Lumbre Burger: bench.reserve backup` delivered as a candidate-facing message. That is a real defect (internal action name leaked to the candidate), not a scoring artifact.
3. Several conversations repeat the AI disclosure verbatim in consecutive turns and ask three questions in one message. Anchor 2 of clarity ("several questions at once") and anchor 1-2 of brevity ("three or more distinct ideas") describe exactly that. Human labels of 4-5 on clarity are optimistic against the anchors.

## Decision

The judge stays as the stricter reference. Calibrating the judge down to match a lenient human scale would hide the defects the judge is catching, including the language drift and the internal token leak. What changes is the agent, not the judge: the next iteration fixes the defects that both the judge and the deterministic checks can see.

## Honest limitations

- In-sample calibration: the same 15 conversations are used to inspect agreement and to justify the decision. A held-out set of 15 more labeled conversations is required before the judge can be called calibrated in the statistical sense.
- The human labels cluster at 4-5 (35 fours, 27 fives, 8 threes, 5 twos, 0 ones), which limits the information the agreement number can carry. A label set spanning the full range would separate judge errors from human leniency more cleanly.
- `gpt-4.1-mini` was used for cost; a stronger judge model may align differently and must be re-measured, not assumed.
