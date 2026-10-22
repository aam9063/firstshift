"""T1 (S1): SQLAlchemy models created by the Alembic migration.

Tests run `alembic upgrade head` against the dev Postgres inside a throwaway
schema (unique name per run) so the dev database itself is never touched by
tests. Seeding (restaurants from mocks/seed/restaurants.csv, open shifts for
the next three weeks) is exercised through the public seed functions.
"""

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import pytest
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.settings import settings

EXPECTED_TABLES = {
    "restaurants",
    "open_shifts",
    "candidates",
    "applications",
    "consents",
    "decisions",
    "first_shifts",
    "bench_entries",
    "audit_events",
    "outbox_messages",
    "events",
}


@contextmanager
def fresh_migrated_schema() -> Iterator[Engine]:
    """Run `alembic upgrade head` into a unique throwaway schema, yield the
    engine pointed at it, then drop the schema."""
    admin = create_engine(settings.database_url)
    schema = f"fs_test_{uuid.uuid4().hex[:12]}"
    with admin.connect() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        conn.commit()
    saved = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"{settings.database_url}?options=-csearch_path%3D{quote(schema)}"
    try:
        from alembic.config import Config

        from alembic import command

        cfg = Config("alembic.ini")
        cfg.set_main_option("script_location", "alembic")
        cfg.set_main_option("prepend_sys_path", ".")
        command.upgrade(cfg, "head")
        engine = create_engine(os.environ["DATABASE_URL"])
        try:
            yield engine
        finally:
            engine.dispose()
    finally:
        if saved is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = saved
        with admin.connect() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            conn.commit()
        admin.dispose()


@pytest.fixture(scope="module")
def migrated_engine() -> Iterator[Engine]:
    with fresh_migrated_schema() as engine:
        yield engine


@pytest.fixture(scope="module")
def seeded_engine(migrated_engine: Engine) -> Iterator[Engine]:
    from app.db.seed import seed_open_shifts, seed_restaurants

    with migrated_engine.begin() as conn:
        seed_restaurants(conn)
        seed_open_shifts(conn)
    yield migrated_engine


def test_migration_creates_all_core_tables(migrated_engine: Engine) -> None:
    inspector = inspect(migrated_engine)
    tables = set(inspector.get_table_names())
    missing = EXPECTED_TABLES - tables
    assert not missing, f"migration did not create: {sorted(missing)}"


def test_seed_restaurants_from_csv(seeded_engine: Engine) -> None:
    from app.db.models import Restaurant

    with Session(seeded_engine) as session:
        rows = session.scalars(select(Restaurant).order_by(Restaurant.code)).all()

    assert len(rows) == 15
    assert [r.code for r in rows] == [f"R{n:03d}" for n in range(1, 16)]
    assert all(r.brand_id == "lumbre" for r in rows)
    # 12 pilot + 3 control (S2); the bench operates only in pilot sites.
    assert sum(1 for r in rows if r.bench_enabled) == 12
    assert all(r.timezone == "Europe/Madrid" for r in rows)
    sol = rows[0]
    assert sol.name == "Lumbre Burger Sol"
    assert sol.city == "Madrid"


def test_seed_restaurants_is_idempotent(seeded_engine: Engine) -> None:
    from app.db.models import Restaurant
    from app.db.seed import seed_restaurants

    with seeded_engine.begin() as conn:
        seed_restaurants(conn)
        count = conn.execute(select(func.count()).select_from(Restaurant)).scalar_one()
    assert count == 15


def test_seed_open_shifts_next_three_weeks(seeded_engine: Engine) -> None:
    from app.db.models import OpenShift, Restaurant

    # The seed anchors its window to the business timezone (Europe/Madrid):
    # first_day is the Madrid day after seeding, covering SEED_DAYS days. The
    # test must use the same anchor, or it flakes after 22:00 UTC in summer,
    # when Madrid is already on the next calendar day.
    from app.db.seed import MADRID, SEED_DAYS

    madrid_today = datetime.now(MADRID).date()
    first_day = madrid_today + timedelta(days=1)
    last_day = first_day + timedelta(days=SEED_DAYS - 1)
    with Session(seeded_engine) as session:
        shifts = session.scalars(select(OpenShift).order_by(OpenShift.starts_at)).all()
        restaurant_ids = set(session.scalars(select(Restaurant.id)).all())

    assert shifts, "no open shifts seeded"
    # Concrete shifts (ADR-002): a start/end datetime, a role, a ShiftGrid link.
    assert all(s.shiftgrid_shift_id for s in shifts)
    assert all(s.role in {"kitchen", "till", "foh", "drive_thru"} for s in shifts)
    assert all(s.status == "open" for s in shifts)
    assert all(s.ends_at > s.starts_at for s in shifts)
    # Window: seeded shifts start on the seed's first day and cover SEED_DAYS.
    assert all(first_day <= s.starts_at.date() <= last_day for s in shifts)
    span_days = {s.starts_at.date() for s in shifts}
    assert max(span_days) - min(span_days) >= timedelta(days=13)
    # Every restaurant got shifts (scope column populated).
    assert {s.restaurant_id for s in shifts} == restaurant_ids
    # Kitchen shifts are food contact (C-L8 hygiene gate).
    assert all(s.requires_food_hygiene for s in shifts if s.role == "kitchen")


def test_candidate_and_application_roundtrip(seeded_engine: Engine) -> None:
    from app.db.models import Application, Candidate, Restaurant

    candidate_id = uuid.uuid4()
    with Session(seeded_engine) as session, session.begin():
        session.add(
            Candidate(
                id=candidate_id,
                brand_id="lumbre",
                first_name="Lucia",
                phone="+34600111222",
                preferred_language="es",
                source="qr",
                state="new",
            )
        )
        restaurant_id = session.scalars(select(Restaurant.id).order_by(Restaurant.code)).first()
        assert restaurant_id is not None
        session.add(
            Application(
                id=uuid.uuid4(),
                candidate_id=candidate_id,
                restaurant_id=restaurant_id,
                state="new",
                entered_at=datetime.now(UTC),
                state_changed_at=datetime.now(UTC),
            )
        )

    with Session(seeded_engine) as session:
        row = session.scalars(
            select(Application).where(Application.candidate_id == candidate_id)
        ).one()
        cand = session.scalars(select(Candidate).where(Candidate.id == candidate_id)).one()

    assert str(row.state) == "new"
    assert row.entered_at is not None
    assert row.state_changed_at is not None
    assert str(cand.state) == "new"
    assert cand.erased_at is None


def test_first_shift_carries_o11_tracking_fields(seeded_engine: Engine) -> None:
    """O11: the hired-to-rota window lives on the FirstShift entity."""
    from app.db.models import Application, Candidate, FirstShift, OpenShift, Restaurant

    with Session(seeded_engine) as session, session.begin():
        candidate_id = uuid.uuid4()
        session.add(
            Candidate(
                id=candidate_id,
                brand_id="lumbre",
                first_name="Marta",
                phone="+34600333444",
                preferred_language="es",
                source="walk_in",
                state="new",
            )
        )
        application_id = uuid.uuid4()
        restaurant_id = session.scalars(select(Restaurant.id).order_by(Restaurant.code)).first()
        session.add(
            Application(
                id=application_id,
                candidate_id=candidate_id,
                restaurant_id=restaurant_id,
                state="new",
                entered_at=datetime.now(UTC),
                state_changed_at=datetime.now(UTC),
            )
        )
        shift_id = session.scalars(select(OpenShift.id).limit(1)).one()
        now = datetime.now(UTC)
        session.add(
            FirstShift(
                id=uuid.uuid4(),
                application_id=application_id,
                open_shift_id=shift_id,
                scheduled_at=now + timedelta(days=2),
                promise_started_at=now,
                rota_unlock_date=(now + timedelta(days=3)).date(),
                current_blocker="docs_missing",
            )
        )

    with Session(seeded_engine) as session:
        row = session.scalars(
            select(FirstShift).where(FirstShift.application_id == application_id)
        ).one()

    assert str(row.confirmation_status) == "pending"
    assert str(row.current_blocker) == "docs_missing"
    assert row.docs_complete_at is None
    assert row.csv_confirmed_at is None
    assert row.ready_for_rota_signaled_at is None
    assert row.role_on_day1 is None
