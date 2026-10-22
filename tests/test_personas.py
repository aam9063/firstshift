"""T1 (S1): persona schema and seeded generator (specs/05-iteration-evals.md
section 1).

Spec, verbatim: "Create `evals/personas/` with at least 40 personas generated
from a schema (seeded), covering the real mix of the client" over the axes
profile, languages, writing style, availability and behavior, "Ground truth
per persona: which open shifts are a real fit, whether they would show up
(hidden "reliability" parameter), and what would make them drop out."

These tests run against the public generator and schema only; the CLI
determinism check writes into a temp directory, never into the repo.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from evals.personas.generate import (
    SHIFT_SEED_DATE,
    axis_coverage,
    build_persona_file,
    generate_personas,
    main,
)
from evals.personas.schema import (
    AvailabilityBand,
    Behaviour,
    Language,
    PersonaFile,
    Profile,
    WritingStyle,
)
from mocks.services.seed import generate_open_shifts, load_restaurants

COUNT = 44


def _personas() -> list:
    return generate_personas(seed=42, count=COUNT)


def _shifts_by_id() -> dict:
    shifts = generate_open_shifts(load_restaurants(), SHIFT_SEED_DATE)
    return {shift.shiftgrid_shift_id: shift for shift in shifts}


def _restaurant_ids() -> set[str]:
    return {r.restaurant_id for r in load_restaurants()}


# ------------------------------------------------------------- determinism


def test_generation_is_deterministic_for_seed_42() -> None:
    first = [p.model_dump() for p in generate_personas(seed=42, count=COUNT)]
    second = [p.model_dump() for p in generate_personas(seed=42, count=COUNT)]
    assert first == second


def test_different_seed_produces_different_personas() -> None:
    a = [p.model_dump() for p in generate_personas(seed=42, count=COUNT)]
    b = [p.model_dump() for p in generate_personas(seed=43, count=COUNT)]
    assert a != b


def test_cli_writes_deterministic_file(tmp_path: Path) -> None:
    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"
    assert main(["--seed", "42", "--count", str(COUNT), "--out", str(out_a)]) == 0
    assert main(["--seed", "42", "--count", str(COUNT), "--out", str(out_b)]) == 0
    assert out_a.read_bytes() == out_b.read_bytes()
    loaded = PersonaFile.model_validate_json(out_a.read_text(encoding="utf-8"))
    assert loaded.seed == 42
    assert loaded.count == COUNT
    assert len(loaded.personas) == COUNT


# ------------------------------------------------------------ count, axes


def test_at_least_40_personas() -> None:
    assert len(_personas()) >= 40


def test_every_axis_value_covered_at_least_twice() -> None:
    coverage = axis_coverage(generate_personas(seed=42, count=COUNT))
    for axis, enum_type in (
        ("profile", Profile),
        ("language", Language),
        ("writing_style", WritingStyle),
        ("availability", AvailabilityBand),
        ("behaviour", Behaviour),
    ):
        for value in enum_type:
            assert coverage[axis][value.value] >= 2, (axis, value, coverage[axis])


def test_persona_ids_are_unique_and_stable() -> None:
    personas = _personas()
    ids = [p.persona_id for p in personas]
    assert len(set(ids)) == len(ids)
    assert generate_personas(seed=42, count=COUNT)[0].persona_id == ids[0]


# ------------------------------------------------------------ ground truth


def test_ground_truth_present_and_valid() -> None:
    shifts_by_id = _shifts_by_id()
    restaurant_ids = _restaurant_ids()
    for persona in _personas():
        assert persona.restaurant_id in restaurant_ids
        assert len(persona.fitting_shift_ids) >= 1, persona.persona_id
        for shift_id in persona.fitting_shift_ids:
            shift = shifts_by_id[shift_id]
            assert shift.restaurant_id == persona.restaurant_id
        assert 0.0 <= persona.reliability <= 1.0
        assert persona.dropout_trigger.strip() != ""


def test_evening_weekend_fit_means_friday_or_saturday_evening() -> None:
    shifts_by_id = _shifts_by_id()
    for persona in _personas():
        if persona.availability is not AvailabilityBand.evenings_weekends:
            continue
        assert persona.fitting_shift_ids, persona.persona_id
        for shift_id in persona.fitting_shift_ids:
            starts_at = shifts_by_id[shift_id].starts_at
            assert starts_at.weekday() in (4, 5), shift_id
            assert starts_at.hour >= 17, shift_id


def test_weekday_morning_fit_means_weekday_before_noon() -> None:
    shifts_by_id = _shifts_by_id()
    for persona in _personas():
        if persona.availability is not AvailabilityBand.weekday_mornings:
            continue
        assert persona.fitting_shift_ids, persona.persona_id
        for shift_id in persona.fitting_shift_ids:
            starts_at = shifts_by_id[shift_id].starts_at
            assert starts_at.weekday() <= 4, shift_id
            assert starts_at.hour < 12, shift_id


def test_persona_file_roundtrip_carries_ground_truth() -> None:
    persona_file = build_persona_file(seed=42, count=COUNT)
    restored = PersonaFile.model_validate_json(persona_file.model_dump_json())
    assert restored.personas == persona_file.personas
    first = restored.personas[0]
    assert first.fitting_shift_ids and 0.0 <= first.reliability <= 1.0


def test_generator_uses_fixed_shift_date_not_today() -> None:
    assert isinstance(SHIFT_SEED_DATE, date)
    assert datetime.combine(SHIFT_SEED_DATE, datetime.min.time()) < (
        datetime.now() - timedelta(days=30)
    )
