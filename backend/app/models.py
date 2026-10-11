from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import get_settings
from .db import Base, Embedding, utcnow

EMBEDDING_DIM = get_settings().embedding_dim


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft | live | paused | ended
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    registration_open: Mapped[bool] = mapped_column(Boolean, default=True)
    wrong_penalty: Mapped[int] = mapped_column(Integer, default=5)
    min_points: Mapped[int] = mapped_column(Integer, default=20)
    # Shown only to teams that have solved every stage.
    final_message: Mapped[str] = mapped_column(Text, default="")
    # Participation: team_size 1 means everyone plays alone.
    team_size: Mapped[int] = mapped_column(Integer, default=4)
    questions_per_team: Mapped[int | None] = mapped_column(Integer)  # None = every question
    duration_minutes: Mapped[int | None] = mapped_column(Integer)  # None = runs until an admin ends it
    # Scoring defaults. Each puzzle and hint keeps its own value; these fill in new ones.
    default_points: Mapped[int] = mapped_column(Integer, default=100)
    hint_costs: Mapped[list] = mapped_column(JSON, default=lambda: [10, 20, 30])
    completion_bonus: Mapped[int] = mapped_column(Integer, default=100)
    # Map: placeholder (built-in schematic) | image (your campus map) | osm (OpenStreetMap tiles)
    map_provider: Mapped[str] = mapped_column(String(16), default="placeholder")
    map_image_url: Mapped[str] = mapped_column(String(500), default="")
    map_lat: Mapped[float | None] = mapped_column(Float)
    map_lng: Mapped[float | None] = mapped_column(Float)
    map_zoom: Mapped[int] = mapped_column(Integer, default=17)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("event_id", "name_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(40))
    name_key: Mapped[str] = mapped_column(String(40))  # lowercased, for case-insensitive uniqueness
    password_hash: Mapped[str] = mapped_column(String(200))
    members: Mapped[list] = mapped_column(JSON, default=list)
    score: Mapped[int] = mapped_column(Integer, default=0)
    disqualified: Mapped[bool] = mapped_column(Boolean, default=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Puzzle(Base):
    __tablename__ = "puzzles"
    __table_args__ = (UniqueConstraint("event_id", "stage"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    stage: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(120))
    cipher: Mapped[str] = mapped_column(String(24))
    prompt: Mapped[str] = mapped_column(Text, default="")
    encoded_text: Mapped[str] = mapped_column(Text, default="")
    points: Mapped[int] = mapped_column(Integer, default=100)
    # HMAC digests of the accepted answers. Plaintext answers are never stored.
    answer_hashes: Mapped[list] = mapped_column(JSON, default=list)

    hints: Mapped[list["Hint"]] = relationship(
        order_by="Hint.position", cascade="all, delete-orphan", passive_deletes=True
    )


class Hint(Base):
    __tablename__ = "hints"

    id: Mapped[int] = mapped_column(primary_key=True)
    puzzle_id: Mapped[int] = mapped_column(ForeignKey("puzzles.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=1)
    text: Mapped[str] = mapped_column(Text)
    penalty: Mapped[int] = mapped_column(Integer, default=10)


class Progress(Base):
    __tablename__ = "progress"
    __table_args__ = (UniqueConstraint("team_id", "puzzle_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    puzzle_id: Mapped[int] = mapped_column(ForeignKey("puzzles.id", ondelete="CASCADE"))
    wrong_attempts: Mapped[int] = mapped_column(Integer, default=0)
    hints_used: Mapped[int] = mapped_column(Integer, default=0)
    penalty_total: Mapped[int] = mapped_column(Integer, default=0)  # points already deducted on this puzzle
    points_awarded: Mapped[int] = mapped_column(Integer, default=0)  # net: puzzle points minus penalty_total
    solved_at: Mapped[datetime | None] = mapped_column(DateTime)


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    puzzle_id: Mapped[int] = mapped_column(ForeignKey("puzzles.id", ondelete="CASCADE"))
    answer: Mapped[str] = mapped_column(String(200))
    correct: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    content: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(12), default="genuine")  # genuine | decoy (admin-only label)
    stage: Mapped[int] = mapped_column(Integer, default=0)  # searchable once the team reaches this stage
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DocChunk(Base):
    __tablename__ = "doc_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[int] = mapped_column(Integer, index=True)
    stage: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(160))
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list] = mapped_column(Embedding(EMBEDDING_DIM))


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(12), default="chat")  # chat | hint | blocked
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (UniqueConstraint("event_id", "identifier"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    identifier: Mapped[str | None] = mapped_column(String(80))  # roll number or email; unique when given
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Assignment(Base):
    """A team's own question list. Teams without rows play the event's questions in stage order."""

    __tablename__ = "assignments"
    __table_args__ = (UniqueConstraint("team_id", "puzzle_id"), UniqueConstraint("team_id", "position"))

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    puzzle_id: Mapped[int] = mapped_column(ForeignKey("puzzles.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)


class ScoreEvent(Base):
    """Append-only ledger. A team's score is always the sum of its rows."""

    __tablename__ = "score_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    puzzle_id: Mapped[int | None] = mapped_column(ForeignKey("puzzles.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(12))  # correct | wrong | hint | bonus | adjust
    delta: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(String(200), default="")
    # Set for anything that may happen only once (a solve, a given hint, the bonus), so the
    # database itself rejects a second copy even if two requests race.
    dedupe_key: Mapped[str | None] = mapped_column(String(80), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MapMarker(Base):
    __tablename__ = "map_markers"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    directions: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(12), default="landmark")  # landmark | clue | final
    # always | stage_reached | stage_solved | finished. Locked markers never leave the server.
    unlock: Mapped[str] = mapped_column(String(16), default="always")
    unlock_stage: Mapped[int | None] = mapped_column(Integer)
    x: Mapped[float] = mapped_column(Float, default=50)  # percent across the placeholder or image map
    y: Mapped[float] = mapped_column(Float, default=50)
    lat: Mapped[float | None] = mapped_column(Float)  # for the osm provider
    lng: Mapped[float | None] = mapped_column(Float)
