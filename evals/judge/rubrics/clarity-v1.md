# Rubric: clarity-v1

criterion: clarity
version: v1

## What it measures

Whether the agent's outbound messages are easy to act on for a busy, often
distressed reader on WhatsApp: one concrete idea per message, one question at
a time, no jargon, no ambiguity about what the candidate should do next.

## Score anchors

### 1
Messages are confusing or self-contradictory. The candidate must reread or
guess what is being asked. Multiple unrelated questions or actions are mixed
into one message, or the message contradicts an earlier one.

### 2
Mostly confusing. The intent is recoverable but buried in noise, jargon or
several questions at once. The candidate would plausibly answer the wrong
question.

### 3
Understandable but uneven. One or two messages need effort to parse or ask
more than one question. The candidate can proceed without asking again.

### 4
Clear throughout. Each message has one purpose and, when a question is asked,
exactly one concrete question. Little or no jargon. The next step is always
obvious.

### 5
Exemplary clarity. Every message is immediately actionable on a phone screen:
one idea, one concrete question where needed, plain words, and the next step
is unambiguous without any follow-up.

## Output shape

The judge replies with exactly this JSON object and nothing else:

```json
{"criterion": "clarity", "score": <integer 1-5>, "rationale": "<one or two sentences citing specific turns as evidence>"}
```
