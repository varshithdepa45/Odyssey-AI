"""Organiser operations added with flexible participation: people, question assignments, map markers,
and the audit trail. Same access rule as admin.py: every route needs an admin token."""

import csv
import io
import random
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db, iso
from ..models import Assignment, Event, MapMarker, Participant, Progress, Puzzle, ScoreEvent, Submission, Team
from ..security import current_admin, hash_password
from ..service import event_puzzles, invalidate_leaderboard, sync_members, team_puzzles
from .admin import _apply, _event, _get, csv_response

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(current_admin)])

CODE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no look-alikes such as 0/o or 1/l


class ParticipantBody(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=60)
    identifier: str | None = Field(None, max_length=80)
    team_id: int | None = None  # 0 removes the participant from their team


class ImportBody(BaseModel):
    csv: str = Field(min_length=1, max_length=200_000)


class TeamCreateBody(BaseModel):
    name: str = Field(min_length=2, max_length=40)
    password: str | None = Field(None, min_length=6, max_length=128)


class AutoTeamsBody(BaseModel):
    prefix: str = Field("Team", min_length=1, max_length=20)
    shuffle: bool = False


class AssignBody(BaseModel):
    questions: list[int] = Field(max_length=99)  # question numbers in play order; empty = event default


class AutoAssignBody(BaseModel):
    count: int | None = Field(None, ge=1, le=99)
    shuffle: bool = False  # false = rotate start points so teams spread out; true = random pick
    overwrite: bool = False  # replace assignments that already exist


class MarkerBody(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, max_length=2000)
    directions: str | None = Field(None, max_length=2000)
    kind: Literal["landmark", "clue", "final"] | None = None
    unlock: Literal["always", "stage_reached", "stage_solved", "finished"] | None = None
    unlock_stage: int | None = Field(None, ge=1, le=99)
    x: float | None = Field(None, ge=0, le=100)
    y: float | None = Field(None, ge=0, le=100)
    lat: float | None = Field(None, ge=-90, le=90)
    lng: float | None = Field(None, ge=-180, le=180)


def _password() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))


def _team_count(db: Session, team_id: int) -> int:
    return db.scalar(select(func.count()).select_from(Participant).where(Participant.team_id == team_id))


def _new_team(db: Session, event: Event, name: str, password: str | None = None) -> tuple[Team, str]:
    """Creates a team, numbering the name if it is taken. Returns the team and its sign-in password."""
    taken = set(db.scalars(select(Team.name_key).where(Team.event_id == event.id)))
    base, candidate, n = " ".join(name.split())[:36], " ".join(name.split())[:40], 2
    while candidate.lower() in taken:
        candidate, n = f"{base} {n}", n + 1
    password = password or _password()
    team = Team(event_id=event.id, name=candidate, name_key=candidate.lower(), password_hash=hash_password(password), members=[])
    db.add(team)
    db.flush()
    return team, password


def _join(db: Session, event: Event, participant: Participant, team: Team) -> None:
    if team.event_id != event.id:
        raise HTTPException(422, "That team belongs to a different event")
    if participant.team_id != team.id and _team_count(db, team.id) >= event.team_size:
        raise HTTPException(409, f"{team.name} is full ({event.team_size} per team)")
    participant.team_id = team.id


def participant_out(p: Participant, teams: dict[int, str]) -> dict:
    return {"id": p.id, "name": p.name, "identifier": p.identifier or "", "team_id": p.team_id, "team": teams.get(p.team_id, "")}


# ---- participants and teams ----

@router.get("/participants")
def list_participants(event_id: int | None = None, db: Session = Depends(get_db)):
    event = _event(db, event_id)
    teams = dict(db.execute(select(Team.id, Team.name).where(Team.event_id == event.id)).all())
    people = db.scalars(select(Participant).where(Participant.event_id == event.id).order_by(Participant.id))
    return {
        "team_size": event.team_size,
        "participants": [participant_out(p, teams) for p in people],
        "teams": [{"id": i, "name": n} for i, n in sorted(teams.items(), key=lambda t: t[1].lower())],
    }


@router.post("/participants")
def add_participant(body: ParticipantBody, event_id: int | None = None, db: Session = Depends(get_db)):
    event = _event(db, event_id)
    if not body.name:
        raise HTTPException(422, "A participant needs a name")
    person = Participant(event_id=event.id, name=body.name.strip(), identifier=(body.identifier or "").strip() or None)
    db.add(person)
    team = _get(db, Team, body.team_id) if body.team_id else None
    try:
        db.flush()
        if team:
            _join(db, event, person, team)
            sync_members(db, team)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"A participant with identifier {body.identifier!r} is already registered")
    return participant_out(person, {team.id: team.name} if team else {})


@router.patch("/participants/{participant_id}")
def update_participant(participant_id: int, body: ParticipantBody, db: Session = Depends(get_db)):
    person = _get(db, Participant, participant_id)
    event = _get(db, Event, person.event_id)
    old_team = db.get(Team, person.team_id) if person.team_id else None
    if body.name:
        person.name = body.name.strip()
    if body.identifier is not None:
        person.identifier = body.identifier.strip() or None
    new_team = old_team
    if body.team_id is not None:
        new_team = _get(db, Team, body.team_id) if body.team_id else None
        if new_team:
            _join(db, event, person, new_team)
        else:
            person.team_id = None
    try:
        for team in {t.id: t for t in (old_team, new_team) if t}.values():
            sync_members(db, team)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Another participant already has that identifier")
    invalidate_leaderboard()
    return participant_out(person, {new_team.id: new_team.name} if new_team else {})


@router.delete("/participants/{participant_id}")
def delete_participant(participant_id: int, db: Session = Depends(get_db)):
    person = _get(db, Participant, participant_id)
    team = db.get(Team, person.team_id) if person.team_id else None
    db.delete(person)
    if team:
        sync_members(db, team)
    db.commit()
    invalidate_leaderboard()
    return {"ok": True}


@router.post("/participants/import")
def import_participants(body: ImportBody, event_id: int | None = None, db: Session = Depends(get_db)):
    """CSV with columns name, identifier, team. Only name is required; a header row is optional.

    A team column puts the participant in that team, creating it if needed. Rows that would duplicate
    an identifier or overfill a team are skipped and reported, and the rest still import.
    """
    event = _event(db, event_id)
    known = {i for i in db.scalars(select(Participant.identifier).where(Participant.event_id == event.id)) if i}
    teams = {t.name_key: t for t in db.scalars(select(Team).where(Team.event_id == event.id))}
    sizes = {t.id: _team_count(db, t.id) for t in teams.values()}
    created, skipped, credentials, touched = 0, [], [], {}
    for line, row in enumerate(csv.reader(io.StringIO(body.csv.strip())), 1):
        cells = [c.strip() for c in row] + ["", "", ""]
        name, identifier, team_name = cells[0][:60], cells[1][:80], " ".join(cells[2].split())[:40]
        if line == 1 and name.lower() in ("name", "participant", "full name"):
            continue
        if not name:
            if any(cells):
                skipped.append({"line": line, "reason": "No name"})
            continue
        if identifier and identifier in known:
            skipped.append({"line": line, "reason": f"Identifier {identifier} is already registered"})
            continue
        team = None
        if team_name:
            team = teams.get(team_name.lower())
            if team and sizes[team.id] >= event.team_size:
                skipped.append({"line": line, "reason": f"{team.name} is full ({event.team_size} per team)"})
                continue
            if not team:
                if len(team_name) < 2:
                    skipped.append({"line": line, "reason": "Team name is too short"})
                    continue
                team, password = _new_team(db, event, team_name)
                teams[team.name_key], sizes[team.id] = team, 0
                credentials.append({"team": team.name, "password": password})
            sizes[team.id] += 1
            touched[team.id] = team
        db.add(Participant(event_id=event.id, name=name, identifier=identifier or None, team_id=team.id if team else None))
        if identifier:
            known.add(identifier)
        created += 1
    for team in touched.values():
        sync_members(db, team)
    db.commit()
    invalidate_leaderboard()
    return {"created": created, "skipped": skipped, "credentials": credentials}


@router.post("/teams")
def create_team(body: TeamCreateBody, event_id: int | None = None, db: Session = Depends(get_db)):
    event = _event(db, event_id)
    name = " ".join(body.name.split())
    if db.scalars(select(Team).where(Team.event_id == event.id, Team.name_key == name.lower())).first():
        raise HTTPException(409, "That team name is taken")
    team, password = _new_team(db, event, name, body.password)
    db.commit()
    invalidate_leaderboard()
    return {"team_id": team.id, "team": team.name, "password": password}


@router.post("/teams/auto")
def auto_form_teams(body: AutoTeamsBody, event_id: int | None = None, db: Session = Depends(get_db)):
    """Groups every unassigned participant into teams of the event's team size. With a team size of 1
    each participant gets their own entry, named after them. Passwords are returned once, here."""
    event = _event(db, event_id)
    people = list(db.scalars(
        select(Participant).where(Participant.event_id == event.id, Participant.team_id.is_(None)).order_by(Participant.id)
    ))
    if not people:
        raise HTTPException(409, "Everyone already has a team")
    if body.shuffle:
        random.shuffle(people)
    credentials = []
    existing = db.scalar(select(func.count()).select_from(Team).where(Team.event_id == event.id))
    for index, start in enumerate(range(0, len(people), event.team_size), 1):
        group = people[start:start + event.team_size]
        name = group[0].name if event.team_size == 1 else f"{body.prefix} {existing + index:02d}"
        if len(name) < 2:
            name = f"{body.prefix} {existing + index:02d}"
        team, password = _new_team(db, event, name)
        for person in group:
            person.team_id = team.id
        sync_members(db, team)
        credentials.append({"team": team.name, "password": password, "members": [p.name for p in group]})
    db.commit()
    invalidate_leaderboard()
    return {"teams": len(credentials), "credentials": credentials}


# ---- question assignments ----

def _replace_assignments(db: Session, team: Team, puzzles: list[Puzzle]) -> None:
    db.execute(delete(Assignment).where(Assignment.team_id == team.id))
    db.flush()
    for position, puzzle in enumerate(puzzles, 1):
        db.add(Assignment(team_id=team.id, puzzle_id=puzzle.id, position=position))


@router.get("/assignments")
def list_assignments(event_id: int | None = None, db: Session = Depends(get_db)):
    event = _event(db, event_id)
    custom = set(db.scalars(select(Assignment.team_id).join(Team, Team.id == Assignment.team_id).where(Team.event_id == event.id)))
    solved: dict[int, int] = {}
    for team_id in db.scalars(
        select(Progress.team_id).join(Team, Team.id == Progress.team_id)
        .where(Team.event_id == event.id, Progress.solved_at.is_not(None))
    ):
        solved[team_id] = solved.get(team_id, 0) + 1
    teams = db.scalars(select(Team).where(Team.event_id == event.id).order_by(Team.name_key))
    return {
        "available": [{"question": p.stage, "title": p.title, "cipher": p.cipher} for p in event_puzzles(db, event.id)],
        "teams": [
            {
                "team_id": t.id, "team": t.name, "custom": t.id in custom, "solved": solved.get(t.id, 0),
                "questions": [p.stage for p in team_puzzles(db, event, t.id)],
            }
            for t in teams
        ],
    }


@router.put("/teams/{team_id}/assignments")
def set_assignments(team_id: int, body: AssignBody, db: Session = Depends(get_db)):
    team = _get(db, Team, team_id)
    if team.finished_at:
        raise HTTPException(409, "This team has finished. Reset its progress before changing its questions.")
    if len(set(body.questions)) != len(body.questions):
        raise HTTPException(422, "A question can be assigned to a team only once")
    by_number = {p.stage: p for p in event_puzzles(db, team.event_id)}
    unknown = [q for q in body.questions if q not in by_number]
    if unknown:
        raise HTTPException(422, f"No such question in this event: {', '.join(map(str, unknown))}")
    chosen = [by_number[q] for q in body.questions]
    if chosen:
        touched = set(db.scalars(select(Progress.puzzle_id).where(Progress.team_id == team.id)))
        missing = sorted(p.stage for p in by_number.values() if p.id in touched and p not in chosen)
        if missing:
            raise HTTPException(409, f"The team has already worked on question {missing[0]}; keep it in the list")
    _replace_assignments(db, team, chosen)
    db.commit()
    invalidate_leaderboard()
    return {"team_id": team.id, "questions": [p.stage for p in team_puzzles(db, _get(db, Event, team.event_id), team.id)]}


@router.post("/assignments/auto")
def auto_assign(body: AutoAssignBody, event_id: int | None = None, db: Session = Depends(get_db)):
    """Gives each team `count` questions. Teams that have started playing are left alone."""
    event = _event(db, event_id)
    puzzles = event_puzzles(db, event.id)
    count = body.count or event.questions_per_team or len(puzzles)
    if not puzzles or count > len(puzzles):
        raise HTTPException(422, f"Asked for {count} questions per team but the event has {len(puzzles)}")
    started = set(db.scalars(select(Progress.team_id)))
    custom = set(db.scalars(select(Assignment.team_id)))
    assigned, skipped = 0, []
    teams = db.scalars(select(Team).where(Team.event_id == event.id).order_by(Team.id)).all()
    for index, team in enumerate(teams):
        if team.id in started:
            skipped.append({"team": team.name, "reason": "already playing"})
        elif team.id in custom and not body.overwrite:
            skipped.append({"team": team.name, "reason": "already assigned"})
        else:
            if body.shuffle:
                chosen = sorted(random.sample(puzzles, count), key=lambda p: p.stage)
            else:
                chosen = [puzzles[(index + k) % len(puzzles)] for k in range(count)]
            _replace_assignments(db, team, chosen)
            assigned += 1
    db.commit()
    invalidate_leaderboard()
    return {"assigned": assigned, "per_team": count, "skipped": skipped}


# ---- map markers ----

MARKER_FIELDS = ("name", "description", "directions", "kind", "unlock", "unlock_stage", "x", "y", "lat", "lng")


def marker_out(m: MapMarker) -> dict:
    return {"id": m.id, **{field: getattr(m, field) for field in MARKER_FIELDS}}


def _check_marker(marker: MapMarker) -> None:
    if marker.unlock in ("stage_reached", "stage_solved") and not marker.unlock_stage:
        raise HTTPException(422, "Choose which question unlocks this marker")
    if marker.unlock in ("always", "finished"):
        marker.unlock_stage = None
    if (marker.lat is None) != (marker.lng is None):
        raise HTTPException(422, "Give both latitude and longitude, or neither")


@router.get("/markers")
def list_markers(event_id: int | None = None, db: Session = Depends(get_db)):
    event = _event(db, event_id)
    return [marker_out(m) for m in db.scalars(select(MapMarker).where(MapMarker.event_id == event.id).order_by(MapMarker.id))]


@router.post("/markers")
def create_marker(body: MarkerBody, event_id: int | None = None, db: Session = Depends(get_db)):
    event = _event(db, event_id)
    if not body.name:
        raise HTTPException(422, "A marker needs a name")
    marker = MapMarker(event_id=event.id, kind="landmark", unlock="always", x=50, y=50, description="", directions="")
    _apply(marker, body, MARKER_FIELDS)
    _check_marker(marker)
    db.add(marker)
    db.commit()
    return marker_out(marker)


@router.patch("/markers/{marker_id}")
def update_marker(marker_id: int, body: MarkerBody, db: Session = Depends(get_db)):
    marker = _get(db, MapMarker, marker_id)
    _apply(marker, body, MARKER_FIELDS)
    for field in ("lat", "lng"):  # these two can be cleared by sending null
        if field in body.model_fields_set and getattr(body, field) is None:
            setattr(marker, field, None)
    _check_marker(marker)
    db.commit()
    return marker_out(marker)


@router.delete("/markers/{marker_id}")
def delete_marker(marker_id: int, db: Session = Depends(get_db)):
    db.delete(_get(db, MapMarker, marker_id))
    db.commit()
    return {"ok": True}


# ---- audit trail ----

def _history(db: Session, event: Event, limit: int | None):
    query = (
        select(ScoreEvent, Team.name, Puzzle.stage)
        .join(Team, Team.id == ScoreEvent.team_id).outerjoin(Puzzle, Puzzle.id == ScoreEvent.puzzle_id)
        .where(Team.event_id == event.id).order_by(ScoreEvent.id.desc())
    )
    return db.execute(query.limit(limit) if limit else query).all()


@router.get("/history")
def score_history(event_id: int | None = None, kind: str | None = None, db: Session = Depends(get_db)):
    """The score ledger, newest first. kind=hint gives the hint log."""
    rows = _history(db, _event(db, event_id), None if kind else 300)
    return [
        {"team": team, "question": stage, "kind": e.kind, "delta": e.delta, "note": e.note, "at": iso(e.created_at)}
        for e, team, stage in rows if not kind or e.kind == kind
    ][:300]


@router.get("/export/history.csv")
def export_history(event_id: int | None = None, db: Session = Depends(get_db)):
    event = _event(db, event_id)
    rows = ((iso(e.created_at), team, stage, e.kind, e.delta, e.note) for e, team, stage in reversed(_history(db, event, None)))
    return csv_response(f"codehunt-score-history-{event.id}.csv", ["time", "team", "question", "kind", "points", "note"], rows)


@router.get("/export/attempts.csv")
def export_attempts(event_id: int | None = None, db: Session = Depends(get_db)):
    event = _event(db, event_id)
    found = db.execute(
        select(Submission, Team.name, Puzzle.stage)
        .join(Team, Team.id == Submission.team_id).join(Puzzle, Puzzle.id == Submission.puzzle_id)
        .where(Team.event_id == event.id).order_by(Submission.id)
    ).all()
    rows = ((iso(s.created_at), team, stage, "correct" if s.correct else "wrong", s.answer) for s, team, stage in found)
    return csv_response(f"codehunt-attempts-{event.id}.csv", ["time", "team", "question", "result", "wrong_answer"], rows)


@router.get("/export/participants.csv")
def export_participants(event_id: int | None = None, db: Session = Depends(get_db)):
    event = _event(db, event_id)
    found = db.execute(
        select(Participant, Team.name).outerjoin(Team, Team.id == Participant.team_id)
        .where(Participant.event_id == event.id).order_by(Team.name, Participant.id)
    ).all()
    rows = ((p.name, p.identifier, team) for p, team in found)
    return csv_response(f"codehunt-participants-{event.id}.csv", ["name", "identifier", "team"], rows)
