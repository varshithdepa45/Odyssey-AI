"""Game rules shared by the routers: the active event, question order, scoring, ranking and map unlocks.

Every score change goes through record_score, which writes the ledger row and updates the team total in
the same transaction. Nothing in the frontend computes a score.
"""

import time
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import iso, utcnow
from .models import Assignment, Event, MapMarker, Participant, Progress, Puzzle, ScoreEvent, Team

_board_cache: dict[tuple, tuple[float, list]] = {}
BOARD_TTL = 3  # seconds; absorbs leaderboard polling between score changes

TIE_BREAKS = "Higher score, then more questions solved, then earlier finish, then earlier last solve, then fewer hints."


# ---- event ----

def active_event(db: Session) -> Event | None:
    return db.scalars(select(Event).where(Event.is_active).order_by(Event.id.desc())).first()


def ends_at(event: Event) -> datetime | None:
    if event.started_at and event.duration_minutes:
        return event.started_at + timedelta(minutes=event.duration_minutes)
    return None


def require_event(db: Session) -> Event:
    event = active_event(db)
    if not event:
        raise HTTPException(503, "No event is running yet")
    deadline = ends_at(event)
    if event.status == "live" and deadline and utcnow() >= deadline:
        # The clock ran out: close the event the first time anyone notices.
        event.status, event.ended_at = "ended", deadline
        db.commit()
        invalidate_leaderboard()
    return event


def require_live(event: Event) -> None:
    if event.status != "live":
        messages = {"draft": "The hunt has not started yet", "paused": "The hunt is paused", "ended": "The hunt has ended"}
        raise HTTPException(409, messages.get(event.status, "The hunt is not live"))


def rules_summary(event: Event) -> str:
    costs = ", ".join(f"hint {i} costs {cost}" for i, cost in enumerate(event.hint_costs or [], 1))
    parts = [
        f"A correct answer earns the question's points ({event.default_points} by default).",
        f"Each wrong answer costs {event.wrong_penalty} points.",
        f"Hints are revealed one at a time and each must be confirmed first; by default {costs}." if costs else "",
        f"Penalties on a question stop once it would be worth less than {event.min_points} points.",
        f"Finishing every assigned question earns a {event.completion_bonus} point bonus." if event.completion_bonus else "",
        "Questions unlock in order, and answers ignore case, spaces and punctuation.",
        f"The hunt runs for {event.duration_minutes} minutes from the start signal." if event.duration_minutes else "",
        f"Ties are broken in this order: {TIE_BREAKS}",
    ]
    return " ".join(p for p in parts if p)


# ---- question order ----

def event_puzzles(db: Session, event_id: int) -> list[Puzzle]:
    return list(db.scalars(select(Puzzle).where(Puzzle.event_id == event_id).order_by(Puzzle.stage)))


def team_puzzles(db: Session, event: Event, team_id: int) -> list[Puzzle]:
    """The team's questions in play order: its own assignment if it has one, else the event's stage order."""
    assigned = list(db.scalars(
        select(Puzzle).join(Assignment, Assignment.puzzle_id == Puzzle.id)
        .where(Assignment.team_id == team_id).order_by(Assignment.position)
    ))
    if assigned:
        return assigned
    puzzles = event_puzzles(db, event.id)
    return puzzles[: event.questions_per_team] if event.questions_per_team else puzzles


def progress_for(db: Session, team_id: int) -> dict[int, Progress]:
    return {p.puzzle_id: p for p in db.scalars(select(Progress).where(Progress.team_id == team_id))}


def current_puzzle(puzzles: list[Puzzle], progress: dict[int, Progress]) -> Puzzle | None:
    """Questions unlock in order: the current one is the first not yet solved."""
    for puzzle in puzzles:
        entry = progress.get(puzzle.id)
        if not (entry and entry.solved_at):
            return puzzle
    return None


def reached_stages(event: Event, puzzles: list[Puzzle], progress: dict[int, Progress]) -> tuple[set[int], set[int]]:
    """(stages the team has opened, stages it has solved). Nothing counts as opened before go-live."""
    solved = {p.stage for p in puzzles if progress.get(p.id) and progress[p.id].solved_at}
    reached = set(solved)
    current = current_puzzle(puzzles, progress)
    if current and event.status != "draft":
        reached.add(current.stage)
    return reached, solved


# ---- scoring ----

def invalidate_leaderboard() -> None:
    _board_cache.clear()


def record_score(db: Session, team: Team, kind: str, delta: int, note: str,
                 puzzle: Puzzle | None = None, dedupe_key: str | None = None) -> None:
    """The only way a score changes. The caller holds the team row lock and commits."""
    db.add(ScoreEvent(
        team_id=team.id, puzzle_id=puzzle.id if puzzle else None, kind=kind, delta=delta,
        note=note[:200], dedupe_key=dedupe_key,
    ))
    team.score += delta
    invalidate_leaderboard()


def penalty_room(event: Event, puzzle: Puzzle, entry: Progress) -> int:
    """How many more points can still be deducted on this question before it hits the floor."""
    floor = min(event.min_points, puzzle.points)
    return max(puzzle.points - floor - entry.penalty_total, 0)


def charge(db: Session, event: Event, team: Team, puzzle: Puzzle, entry: Progress,
           kind: str, cost: int, note: str, dedupe_key: str | None = None) -> int:
    """Deducts up to `cost`, limited by the question's floor. Returns what was actually taken."""
    taken = min(cost, penalty_room(event, puzzle, entry))
    entry.penalty_total += taken
    record_score(db, team, kind, -taken, note, puzzle, dedupe_key)
    return taken


def net_value(puzzle: Puzzle, entry: Progress | None) -> int:
    """What solving the question now would leave the team with, after penalties already paid."""
    return puzzle.points - (entry.penalty_total if entry else 0)


# ---- people ----

def sync_members(db: Session, team: Team) -> None:
    """Keeps the denormalised member list on the team in step with its participants."""
    db.flush()
    names = db.scalars(select(Participant.name).where(Participant.team_id == team.id).order_by(Participant.id))
    team.members = list(names)


# ---- ranking ----

def leaderboard(db: Session, event: Event, include_disqualified: bool = False) -> list[dict]:
    key = (event.id, include_disqualified)
    cached = _board_cache.get(key)
    if cached and time.monotonic() - cached[0] < BOARD_TTL:
        return cached[1]

    teams = list(db.scalars(select(Team).where(Team.event_id == event.id)))
    default_total = len(team_puzzles(db, event, -1))
    assigned: dict[int, int] = {}
    for row in db.scalars(select(Assignment).join(Team, Team.id == Assignment.team_id).where(Team.event_id == event.id)):
        assigned[row.team_id] = assigned.get(row.team_id, 0) + 1
    stats = {t.id: {"solved": 0, "wrong": 0, "hints": 0, "last": None} for t in teams}
    entries = db.scalars(select(Progress).join(Team, Team.id == Progress.team_id).where(Team.event_id == event.id))
    for entry in entries:
        s = stats[entry.team_id]
        s["wrong"] += entry.wrong_attempts
        s["hints"] += entry.hints_used
        if entry.solved_at:
            s["solved"] += 1
            s["last"] = max(s["last"], entry.solved_at) if s["last"] else entry.solved_at

    rows = []
    for team in teams:
        if team.disqualified and not include_disqualified:
            continue
        s = stats[team.id]
        elapsed = None
        if team.finished_at and event.started_at:
            elapsed = max(int((team.finished_at - event.started_at).total_seconds()), 0)
        rows.append({
            "team_id": team.id, "team": team.name, "members": team.members, "score": team.score,
            "solved": s["solved"], "total": assigned.get(team.id, default_total),
            "wrong_attempts": s["wrong"], "hints_used": s["hints"],
            "finished": team.finished_at is not None, "finished_at": iso(team.finished_at),
            "elapsed_seconds": elapsed, "disqualified": team.disqualified,
            "_sort": (
                team.disqualified, -team.score, -s["solved"], team.finished_at or datetime.max,
                s["last"] or datetime.max, s["hints"], team.created_at,
            ),
        })
    rows.sort(key=lambda r: r.pop("_sort"))
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    _board_cache[key] = (time.monotonic(), rows)
    return rows


def question_leaderboard(db: Session, event: Event, puzzle: Puzzle) -> list[dict]:
    """One question's ranking: solvers first, by points kept, then by who solved it sooner."""
    rows = []
    pairs = db.execute(
        select(Progress, Team).join(Team, Team.id == Progress.team_id)
        .where(Progress.puzzle_id == puzzle.id, Team.disqualified.is_(False))
    ).all()
    for entry, team in pairs:
        solved = entry.solved_at is not None
        seconds = None
        if solved and event.started_at:
            seconds = max(int((entry.solved_at - event.started_at).total_seconds()), 0)
        rows.append({
            "team": team.name, "solved": solved,
            "points": entry.points_awarded if solved else -entry.penalty_total,
            "hints_used": entry.hints_used, "wrong_attempts": entry.wrong_attempts, "solved_seconds": seconds,
            "_sort": (not solved, -(entry.points_awarded if solved else -entry.penalty_total),
                      entry.solved_at or datetime.max, entry.hints_used, team.created_at),
        })
    rows.sort(key=lambda r: r.pop("_sort"))
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    return rows


# ---- map ----

def marker_unlocked(marker: MapMarker, reached: set[int], solved: set[int], finished: bool) -> bool:
    if marker.unlock == "always":
        return True
    if marker.unlock == "stage_reached":
        return marker.unlock_stage in reached
    if marker.unlock == "stage_solved":
        return marker.unlock_stage in solved
    if marker.unlock == "finished":
        return finished
    return False


def split_markers(db: Session, event: Event, team: Team) -> tuple[list[MapMarker], list[MapMarker]]:
    """(markers this team may see, markers still hidden from it)."""
    puzzles = team_puzzles(db, event, team.id)
    reached, solved = reached_stages(event, puzzles, progress_for(db, team.id))
    finished = team.finished_at is not None
    markers = db.scalars(select(MapMarker).where(MapMarker.event_id == event.id).order_by(MapMarker.id)).all()
    visible = [m for m in markers if marker_unlocked(m, reached, solved, finished)]
    return visible, [m for m in markers if m not in visible]


def next_step(event: Event, team: Team, current: Puzzle | None, position: int, visible: list[MapMarker]) -> str:
    """A spoiler-free pointer to what the team may do next, built only from what it has unlocked."""
    if event.status == "draft":
        return "The hunt has not started. Wait for the start signal, then open your first question."
    unlocked = [m for m in visible if m.kind != "landmark"]
    latest = unlocked[-1] if unlocked else None
    place = ""
    if latest:
        place = f" Your most recently unlocked map marker is {latest.name}."
        if latest.directions:
            place += f" Directions: {latest.directions}"
    if team.finished_at:
        return "You have solved every question. Open the map and follow the final instructions." + place
    if not current:
        return "No questions are assigned to your team yet. Ask an organiser."
    return f"Decode question {position} ({current.cipher} cipher) and submit the phrase to unlock what comes next." + place
