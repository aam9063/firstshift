# Rubric: brevity-v1

criterion: brevity
version: v1

## What it measures

Whether messages are WhatsApp-sized: short, one screen or less, one idea per
message. Long formal paragraphs, shift lists dumped as walls of text, or
repeated information count against this criterion even if they are polite.

## Score anchors

### 1
Message-wall territory. Multiple messages far beyond one screen, shift lists
dumped in full, or repeated information across turns. The candidate has to
scroll to act.

### 2
Too long more often than not. Several messages exceed a comfortable phone
screen, or one message carries three or more distinct ideas or questions.

### 3
Mixed. Most messages are reasonable but at least one is clearly oversized for
WhatsApp, or information that could be split across turns is crammed into one.

### 4
Consistently short. Messages fit on one phone screen, one idea each, no
repetition. At most one message is slightly longer than ideal.

### 5
Exemplary brevity. Every message is tight and scannable at a glance: short
sentences, at most one question, no repetition, nothing that needs scrolling.

## Output shape

The judge replies with exactly this JSON object and nothing else:

```json
{"criterion": "brevity", "score": <integer 1-5>, "rationale": "<one or two sentences citing specific turns as evidence>"}
```
