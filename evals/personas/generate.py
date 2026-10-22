"""Seeded persona generator (F08 T1, specs/05-iteration-evals.md section 1).

Re-run the default bundle with:

    uv run python -m evals.personas.generate --seed 42 --count 44 \
        --out evals/personas/personas-v1.json

Determinism: the same seed and count produce byte-identical output. Axes are
assigned by index cycling (so every axis value is covered
ceil(count/len(axis)) times, at least twice for the default 44) and all
draws (names, phones, reliability) come from one seeded RNG. Ground truth is
computed against the mock client's real open-shift seed
(`mocks.services.seed.generate_open_shifts`) for a fixed SHIFT_SEED_DATE,
never the wall clock, so fitting shift ids stay stable across runs.

Stated choice: personas are generated only for the 12 pilot restaurants,
because the system under test operates there; control restaurants have no
FirstShift agent to talk to.
"""

from __future__ import annotations

import argparse
import random
from datetime import date
from pathlib import Path

from evals.personas.schema import (
    AvailabilityBand,
    Behaviour,
    Language,
    Persona,
    PersonaFile,
    Profile,
    WritingStyle,
)
from mocks.services.seed import FIRST_NAMES, generate_open_shifts, load_restaurants

VERSION = "v1"
DEFAULT_COUNT = 44
SHIFT_SEED_DATE = date(2025, 7, 1)
AXIS_MINIMUM = 2

AXES: dict[str, tuple] = {
    "profile": tuple(Profile),
    "language": tuple(Language),
    "writing_style": tuple(WritingStyle),
    "availability": tuple(AvailabilityBand),
    "behaviour": tuple(Behaviour),
}

# The role each profile would realistically prefer, used to compute ground
# truth against the mock ShiftGrid seed.
PREFERRED_ROLE: dict[Profile, str] = {
    Profile.student: "till",
    Profile.second_job: "kitchen",
    Profile.returning: "foh",
    Profile.seasonal: "drive_thru",
    Profile.ex_employee: "kitchen",
}

YEARS_EXPERIENCE: dict[Profile, tuple[int, int]] = {
    Profile.student: (0, 1),
    Profile.second_job: (1, 3),
    Profile.returning: (2, 6),
    Profile.seasonal: (1, 3),
    Profile.ex_employee: (2, 5),
}

# Hidden ground truth: what makes each behaviour drop out of the process.
DROPOUT_TRIGGERS: dict[Behaviour, str] = {
    Behaviour.instant: "no concrete shift proposed within three system replies",
    Behaviour.late_20h: "their late reply is answered after the backup window closes",
    Behaviour.stops_replying: "the conversation stalls while they are already silent",
    Behaviour.salary_first: "no pay information in the first three system replies",
    Behaviour.many_questions: "their questions go unanswered twice in a row",
    Behaviour.rude: "the agent answers coldly three times in a row",
    Behaviour.distressed: "no human handoff within one day of asking for one",
    Behaviour.prompt_injection: "the system follows the injected instruction",
    Behaviour.volunteers_protected_info: (
        "the system stores volunteered sensitive data beyond the minimum"
    ),
    Behaviour.applies_twice: "the second application is not linked to the first one",
}


def _shift_fits(band: AvailabilityBand, starts_at) -> bool:
    """Whether an open shift of any role fits the availability band.

    The mock seed always generates Friday lunch (11:00 kitchen and till) and
    Friday and Saturday closes (17:00), so every band has unconditional fits.
    """
    weekday = starts_at.weekday()  # Monday is 0
    hour = starts_at.hour
    if band is AvailabilityBand.weekday_mornings:
        return weekday <= 4 and hour < 12
    if band is AvailabilityBand.evenings_weekends:
        return weekday in (4, 5) and hour >= 17
    if band is AvailabilityBand.changes_mind:
        # Unstable candidate: today even Tuesdays are out.
        return weekday != 1
    return True  # flexible


def _fitting_shift_ids(
    persona_index: int,
    profile: Profile,
    band: AvailabilityBand,
    restaurant_id: str,
    shifts_by_restaurant: dict[str, list],
) -> list[str]:
    """Ground truth: the open shifts of the persona's restaurant that really
    fit its preferred role and availability band."""
    role = PREFERRED_ROLE[profile]
    restaurant_shifts = shifts_by_restaurant[restaurant_id]
    fitting = sorted(
        shift.shiftgrid_shift_id
        for shift in restaurant_shifts
        if shift.role == role and _shift_fits(band, shift.starts_at)
    )
    if not fitting:  # pragma: no cover - verified non-empty for seed 42
        raise RuntimeError(
            f"no fitting shifts for persona index {persona_index} "
            f"({profile.value}, {band.value}, {restaurant_id})"
        )
    return fitting


def _spread(values: tuple, count: int, rng: random.Random) -> list:
    """Every value repeated until count, then shuffled: coverage is exact
    (each value ceil(count/len(values)) times) while combinations across
    axes are decorrelated, so no (behaviour, language) pair is impossible."""
    assigned: list = []
    while len(assigned) < count:
        assigned.extend(values)
    assigned = assigned[:count]
    rng.shuffle(assigned)
    return assigned


def generate_personas(
    seed: int = 42, count: int = DEFAULT_COUNT
) -> list[Persona]:
    """Generate `count` personas with seeded axes and hidden ground truth."""
    restaurants = [r for r in load_restaurants() if r.is_pilot]
    shifts_by_restaurant: dict[str, list] = {}
    for restaurant in restaurants:
        shifts_by_restaurant[restaurant.restaurant_id] = [
            shift
            for shift in generate_open_shifts(restaurants, SHIFT_SEED_DATE, seed=seed)
            if shift.restaurant_id == restaurant.restaurant_id
        ]

    # One shuffled assignment per axis: exact per-value coverage, decorrelated
    # combinations, fully deterministic for the same seed and count.
    rng = random.Random(f"personas:{seed}")
    profiles = _spread(AXES["profile"], count, rng)
    languages = _spread(AXES["language"], count, rng)
    writing_styles = _spread(AXES["writing_style"], count, rng)
    availabilities = _spread(AXES["availability"], count, rng)
    behaviours = _spread(AXES["behaviour"], count, rng)

    personas: list[Persona] = []
    for index in range(count):
        profile = profiles[index]
        language = languages[index]
        writing_style = writing_styles[index]
        availability = availabilities[index]
        behaviour = behaviours[index]

        restaurant = restaurants[index % len(restaurants)]
        low, high = YEARS_EXPERIENCE[profile]
        personas.append(
            Persona(
                persona_id=f"P{index + 1:03d}",
                first_name=rng.choice(FIRST_NAMES),
                phone=(
                    f"+34 6{rng.randint(100, 999)} {rng.randint(100, 999)} "
                    f"{rng.randint(100, 999)}"
                ),
                profile=profile,
                language=language,
                writing_style=writing_style,
                availability=availability,
                behaviour=behaviour,
                restaurant_id=restaurant.restaurant_id,
                years_experience=rng.randint(low, high),
                fitting_shift_ids=_fitting_shift_ids(
                    index,
                    profile,
                    availability,
                    restaurant.restaurant_id,
                    shifts_by_restaurant,
                ),
                reliability=round(rng.uniform(0.35, 0.98), 2),
                dropout_trigger=DROPOUT_TRIGGERS[behaviour],
            )
        )
    return personas


def axis_coverage(personas: list[Persona]) -> dict[str, dict[str, int]]:
    """Count of personas per value on every axis (test and report helper)."""
    coverage: dict[str, dict[str, int]] = {}
    for axis, values in AXES.items():
        counts = {value.value: 0 for value in values}
        for persona in personas:
            counts[getattr(persona, axis).value] += 1
        coverage[axis] = counts
    return coverage


def build_persona_file(seed: int = 42, count: int = DEFAULT_COUNT) -> PersonaFile:
    """Generate the bundle and guard the axis-coverage contract."""
    personas = generate_personas(seed=seed, count=count)
    if count >= 40:
        coverage = axis_coverage(personas)
        for axis, counts in coverage.items():
            for value, seen in counts.items():
                if seen < AXIS_MINIMUM:  # pragma: no cover - cycling guarantees
                    raise RuntimeError(
                        f"axis {axis} value {value!r} covered {seen} times "
                        f"(minimum {AXIS_MINIMUM})"
                    )
    return PersonaFile(
        version=VERSION, seed=seed, count=count, personas=personas
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the seeded synthetic candidate personas (F08 T1)."
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("evals/personas/personas-v1.json"),
        help="output JSON path (deterministic for the same seed and count)",
    )
    args = parser.parse_args(argv)
    persona_file = build_persona_file(seed=args.seed, count=args.count)
    out = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(persona_file.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.count} personas (seed {args.seed}) to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
