"""Persona schema for the eval harness (F08 T1, specs/05-iteration-evals.md
section 1).

A persona covers the real mix of the client across five observable axes
(profile, language, writing style, availability band, behaviour) plus hidden
ground truth used by the eval layers: which open ShiftGrid shifts of a seeded
restaurant are a real fit, a hidden reliability parameter (would they show
up), and the trigger that would make them drop out.

The hidden ground truth is scoring material for the runner, never input to
the conversation: the candidate simulator's observable view
(`evals.personas.simulator.CandidateView`) is built without it, so the
system under test cannot see it through the simulator either.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Profile(StrEnum):
    """Who the candidate is, per the client's real mix."""

    student = "student"
    second_job = "second_job"
    returning = "returning"
    seasonal = "seasonal"
    ex_employee = "ex_employee"


class Language(StrEnum):
    """Conversation language, per the multilingual coastal market."""

    es = "es"
    pt = "pt"
    en = "en"
    mixed = "mixed"


class WritingStyle(StrEnum):
    """How the candidate writes on WhatsApp."""

    typo_heavy = "typo_heavy"
    emoji_heavy = "emoji_heavy"
    voice_note_short = "voice_note_short"


class AvailabilityBand(StrEnum):
    """Concrete availability, not a vague dropdown."""

    weekday_mornings = "weekday_mornings"
    evenings_weekends = "evenings_weekends"
    flexible = "flexible"
    changes_mind = "changes_mind"


class Behaviour(StrEnum):
    """Conversation behaviour under the system's pressure."""

    instant = "instant"
    late_20h = "late_20h"
    stops_replying = "stops_replying"
    salary_first = "salary_first"
    many_questions = "many_questions"
    rude = "rude"
    distressed = "distressed"
    prompt_injection = "prompt_injection"
    volunteers_protected_info = "volunteers_protected_info"
    applies_twice = "applies_twice"


class Persona(BaseModel):
    """One synthetic candidate: observable axes plus hidden ground truth."""

    persona_id: str
    first_name: str
    phone: str
    profile: Profile
    language: Language
    writing_style: WritingStyle
    availability: AvailabilityBand
    behaviour: Behaviour
    restaurant_id: str
    years_experience: int
    # Ground truth: open ShiftGrid shift ids of restaurant_id that really fit.
    fitting_shift_ids: list[str]
    # Hidden: would they show up (0 never, 1 always).
    reliability: float = Field(ge=0.0, le=1.0)
    # Hidden: what makes them drop out of the process.
    dropout_trigger: str


class CandidateView(BaseModel):
    """What the simulator (and through it the system) may know about a
    persona: the candidate's own knowledge only, no hidden ground truth and
    no file paths."""

    persona_id: str
    first_name: str
    language: Language
    writing_style: WritingStyle
    availability: AvailabilityBand
    behaviour: Behaviour
    restaurant_id: str

    @classmethod
    def from_persona(cls, persona: Persona) -> CandidateView:
        """Build the observable view, dropping the hidden ground truth."""
        return cls(
            persona_id=persona.persona_id,
            first_name=persona.first_name,
            language=persona.language,
            writing_style=persona.writing_style,
            availability=persona.availability,
            behaviour=persona.behaviour,
            restaurant_id=persona.restaurant_id,
        )


class PersonaFile(BaseModel):
    """A versioned, seeded bundle of personas (the artifact the runner loads)."""

    version: str
    seed: int
    count: int
    personas: list[Persona]
