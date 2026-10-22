# Rubric: language-v1

criterion: language
version: v1

## What it measures

Whether the whole conversation stays in the candidate's stated preferred
language (Spanish, Portuguese or English), from the first message to the last.
The language is a stated preference, never guessed from a name or from message
content before it is stated. Candidate typos or mixed-language replies do not
count against this criterion; the agent's own output must.

## Score anchors

### 1
The agent converses in the wrong language, or drifts between languages
mid-conversation, or guesses a language from the candidate's name instead of
the stated preference.

### 2
Mostly wrong or unstable. More than one agent message is in a language other
than the stated preference, or the agent switches languages after the
candidate stated one.

### 3
Right language on balance. One or two agent messages slip into another
language (an untranslated word or sentence) but the conversation stays usable
in the stated preference.

### 4
Correct throughout with at most a trivial slip. Every agent message is in the
stated preferred language; any exception is a single borrowed word that any
speaker of the preference language understands.

### 5
Exemplary language discipline. Every agent message from the disclosure onward
is in the stated preferred language, natural and idiomatic, with no drift even
when the candidate switches or mixes languages.

## Output shape

The judge replies with exactly this JSON object and nothing else:

```json
{"criterion": "language", "score": <integer 1-5>, "rationale": "<one or two sentences citing specific turns as evidence>"}
```
