"""Versioned judge rubrics (S4): one markdown file per criterion, parsed into
data the port and the calibration worksheet consume.

Files live in ``evals/judge/rubrics/<criterion>-<version>.md`` and follow a
fixed shape (see clarity-v1.md): a header naming the rubric, ``criterion`` and
``version`` fields, five ``###`` anchor sections for scores 1 to 5, and a JSON
output shape block the judge must reply with. Parsing is strict: a rubric
missing any anchor or a parseable output shape is a load error, so a bad edit
to a rubric file fails CI instead of silently scoring conversations.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

RUBRIC_DIR = Path(__file__).resolve().parent / "rubrics"

# Spec order (specs/05 section 2): clarity, warmth, brevity, language, then
# the no-hallucinated-facts criterion.
EXPECTED_RUBRICS: tuple[str, ...] = ("clarity", "warmth", "brevity", "language", "honesty")

_ANCHOR_RE = re.compile(r"^###\s+([1-5])\s*$", re.MULTILINE)
_FIELD_RE = re.compile(r"^(criterion|version):\s*(\S+)\s*$", re.MULTILINE)
_JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
_PLACEHOLDER_STRING_RE = re.compile(r'"<[^"]*>"')


class RubricError(ValueError):
    """A rubric file is missing, malformed or incomplete."""


@dataclass(frozen=True)
class Rubric:
    """One parsed rubric: one criterion, five anchors, one output shape."""

    name: str  # "<criterion>-<version>", e.g. "clarity-v1"
    criterion: str
    version: str
    description: str
    anchors: dict[int, str] = field(default_factory=dict)
    output_shape: str = ""  # raw JSON template with placeholders

    def concrete_output_shape(self) -> str:
        """The output shape with placeholders substituted, valid JSON.

        Placeholders: ``<integer 1-5>`` becomes a mid-scale 3; ``"<...>"``
        string placeholders become ``"x"``. Used by tests and by the live
        judge's response validator to know what a well-formed reply looks like.
        """
        concrete = self.output_shape.replace("<integer 1-5>", "3")
        concrete = _PLACEHOLDER_STRING_RE.sub('"x"', concrete)
        json.loads(concrete)  # raises RubricError via ValueError if malformed
        return concrete


def _parse(text: str, name: str) -> Rubric:
    fields = dict(_FIELD_RE.findall(text))
    criterion = fields.get("criterion")
    version = fields.get("version")
    if not criterion or not version:
        raise RubricError(f"rubric {name}: missing 'criterion:' or 'version:' field")
    expected_name = f"{criterion}-{version}"
    if name != expected_name:
        raise RubricError(f"rubric {name}: filename does not match '{expected_name}'")

    anchors: dict[int, str] = {}
    matches = list(_ANCHOR_RE.finditer(text))
    if not matches:
        raise RubricError(f"rubric {name}: no '### 1'..'### 5' anchor sections")
    for i, match in enumerate(matches):
        score = int(match.group(1))
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()
        if not body:
            raise RubricError(f"rubric {name}: anchor {score} is empty")
        anchors[score] = body
    if sorted(anchors) != [1, 2, 3, 4, 5]:
        raise RubricError(
            f"rubric {name}: anchors must cover exactly 1 to 5, got {sorted(anchors)}"
        )

    shape_match = _JSON_BLOCK_RE.search(text)
    if shape_match is None:
        raise RubricError(f"rubric {name}: no ```json output shape block")
    output_shape = shape_match.group(1)

    description_match = re.search(r"## What it measures\s*\n\s*\n(.*?)\n\s*\n##", text, re.DOTALL)
    description = description_match.group(1).strip() if description_match else ""

    return Rubric(
        name=name,
        criterion=criterion,
        version=version,
        description=description,
        anchors=anchors,
        output_shape=output_shape,
    )


def load_rubric(name_version: str) -> Rubric:
    """Load one rubric by name, e.g. ``load_rubric("clarity-v1")``."""
    known = _known_names()
    if name_version not in known:
        raise KeyError(f"unknown rubric '{name_version}': expected one of {sorted(_known_names())}")
    path = RUBRIC_DIR / f"{name_version}.md"
    if not path.is_file():
        raise KeyError(f"unknown rubric '{name_version}': missing file {path}")
    return _parse(path.read_text(encoding="utf-8"), name_version)


def load_all_rubrics() -> tuple[Rubric, ...]:
    """Every expected rubric, in spec order. Raises on the first bad file."""
    return tuple(load_rubric(f"{criterion}-v1") for criterion in EXPECTED_RUBRICS)


def _known_names() -> set[str]:
    return {f"{criterion}-v1" for criterion in EXPECTED_RUBRICS}
