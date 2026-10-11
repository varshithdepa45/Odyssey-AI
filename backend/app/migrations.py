"""Versioned schema migrations, applied automatically at startup.

They run inside the app because free hosting tiers give you no shell to run a migration command from.
Each migration runs once, in one transaction, and is recorded in schema_migrations. To change the
schema: update models.py, then append a function here that brings an existing database to match.

    python -m app.migrate      apply pending migrations and print the version
"""

import logging

from sqlalchemy import Column, DateTime, Integer, String, Table, inspect, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from .db import Base, utcnow

log = logging.getLogger("codehunt.migrations")

schema_migrations = Table(
    "schema_migrations", Base.metadata,
    Column("version", Integer, primary_key=True),
    Column("name", String(120), nullable=False),
    Column("applied_at", DateTime, nullable=False),
)


def _add_column(conn: Connection, table: str, name: str, ddl: str) -> None:
    if name not in {c["name"] for c in inspect(conn).get_columns(table)}:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def _v2_flexible_teams_ledger_map(conn: Connection) -> None:
    """Configurable teams and scoring, the score ledger, question assignments and map markers.

    New tables already exist by now (create_all adds missing tables); this adds the new columns to
    old tables and converts existing scores into ledger rows.
    """
    from .models import Participant, Progress, Puzzle, ScoreEvent, Team

    for name, ddl in (
        ("team_size", "INTEGER NOT NULL DEFAULT 4"),
        ("questions_per_team", "INTEGER"),
        ("duration_minutes", "INTEGER"),
        ("default_points", "INTEGER NOT NULL DEFAULT 100"),
        ("hint_costs", "JSON NOT NULL DEFAULT '[10, 20, 30]'"),
        # 0 for events that predate the bonus, so finished teams keep the score they earned.
        ("completion_bonus", "INTEGER NOT NULL DEFAULT 0"),
        ("map_provider", "VARCHAR(16) NOT NULL DEFAULT 'placeholder'"),
        ("map_image_url", "VARCHAR(500) NOT NULL DEFAULT ''"),
        ("map_lat", "FLOAT"),
        ("map_lng", "FLOAT"),
        ("map_zoom", "INTEGER NOT NULL DEFAULT 17"),
    ):
        _add_column(conn, "events", name, ddl)
    _add_column(conn, "progress", "penalty_total", "INTEGER NOT NULL DEFAULT 0")
    _add_column(conn, "chat_messages", "kind", "VARCHAR(12) NOT NULL DEFAULT 'chat'")

    db = Session(bind=conn)
    puzzles = {p.id: p for p in db.scalars(select(Puzzle))}
    ledger: dict[int, int] = {}
    for entry in db.scalars(select(Progress)):
        puzzle = puzzles.get(entry.puzzle_id)
        if not puzzle or not entry.solved_at:
            continue  # penalties on unsolved puzzles were never charged under the old rules
        # Old rule: penalties came off the award at solve time. Record the net award as it was.
        entry.penalty_total = max(puzzle.points - entry.points_awarded, 0)
        db.add(ScoreEvent(
            team_id=entry.team_id, puzzle_id=puzzle.id, kind="correct", delta=entry.points_awarded,
            note=f"Stage {puzzle.stage} solved (migrated, net of penalties)",
            dedupe_key=f"correct:{entry.team_id}:{puzzle.id}", created_at=entry.solved_at,
        ))
        ledger[entry.team_id] = ledger.get(entry.team_id, 0) + entry.points_awarded
    for team in db.scalars(select(Team)):
        gap = team.score - ledger.get(team.id, 0)
        if gap:  # manual adjustments made before the ledger existed
            db.add(ScoreEvent(team_id=team.id, kind="adjust", delta=gap, note="Balance carried over (migrated)"))
        for member in team.members or []:
            db.add(Participant(event_id=team.event_id, team_id=team.id, name=str(member)[:60]))
    db.flush()


def _v3_placeholder_markers(conn: Connection) -> None:
    """Gives events created before the map existed the same placeholder markers a new event gets."""
    from .models import Event, MapMarker
    from .seed import seed_markers

    db = Session(bind=conn)
    for event in db.scalars(select(Event)):
        if not db.scalars(select(MapMarker).where(MapMarker.event_id == event.id)).first():
            seed_markers(db, event, {})
    db.flush()


MIGRATIONS = [
    (1, "baseline", None),
    (2, "flexible teams, score ledger, assignments, map", _v2_flexible_teams_ledger_map),
    (3, "placeholder map markers for existing events", _v3_placeholder_markers),
]
LATEST = MIGRATIONS[-1][0]


def migrate(engine) -> int:
    """Brings the database to the latest version and returns that version."""
    inspector = inspect(engine)
    fresh = not inspector.has_table("events")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        applied = set(conn.execute(select(schema_migrations.c.version)).scalars())

        def stamp(version: int, name: str) -> None:
            conn.execute(schema_migrations.insert().values(version=version, name=name, applied_at=utcnow()))
            applied.add(version)

        if fresh:  # create_all just built the latest schema, so there is nothing to migrate
            for version, name, _ in MIGRATIONS:
                if version not in applied:
                    stamp(version, name)
        elif not applied:  # a database from before migrations existed
            stamp(1, "baseline")
        for version, name, upgrade in MIGRATIONS:
            if version not in applied:
                log.info("Applying migration %s: %s", version, name)
                upgrade(conn)
                stamp(version, name)
    return max(applied)

