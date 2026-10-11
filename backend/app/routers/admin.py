import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import ciphers, rag
from ..db import get_db, iso, utcnow
from ..models import ChatMessage, Document, Event, Hint, Progress, Puzzle, ScoreEvent, Submission, Team
from ..security import answer_hash, current_admin, hash_password, normalize_answer
from ..service import active_event, ends_at, invalidate_leaderboard, leaderboard, record_score

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(current_admin)])

Status = Literal["draft", "live", "paused", "ended"]
Cipher = Literal["binary", "morse", "caesar", "polybius", "vigenere", "hex", "braille", "ascii", "book"]


class EventBody(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=120)
    status: Status | None = None
    registration_open: bool | None = None
    wrong_penalty: int | None = Field(None, ge=0, le=1000)
    min_points: int | None = Field(None, ge=0, le=100000)
    final_message: str | None = Field(None, max_length=4000)
    team_size: int | None = Field(None, ge=1, le=50)
    questions_per_team: int | None = Field(None, ge=0, le=99)  # 0 = every question
    duration_minutes: int | None = Field(None, ge=0, le=100000)  # 0 = no time limit
    default_points: int | None = Field(None, ge=0, le=100000)
    hint_costs: list[int] | None = Field(None, max_length=10)
    completion_bonus: int | None = Field(None, ge=0, le=100000)
    map_provider: Literal["placeholder", "image", "osm"] | None = None
    map_image_url: str | None = Field(None, max_length=500, pattern=r"^(https?://\S+|/\S*)?$")
    map_lat: float | None = Field(None, ge=-90, le=90)
    map_lng: float | None = Field(None, ge=-180, le=180)
    map_zoom: int | None = Field(None, ge=1, le=22)


class TeamBody(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=40)
    score_delta: int | None = Field(None, ge=-100000, le=100000)
    note: str = Field("", max_length=150)  # reason for a score adjustment, kept in the ledger
    disqualified: bool | None = None
    new_password: str | None = Field(None, min_length=6, max_length=128)


class PuzzleBody(BaseModel):
    stage: int | None = Field(None, ge=1, le=99)
    title: str | None = Field(None, min_length=1, max_length=120)
    cipher: Cipher | None = None
    prompt: str | None = Field(None, max_length=4000)
    encoded_text: str | None = Field(None, max_length=8000)
    points: int | None = Field(None, ge=0, le=100000)
    answers: list[str] | None = None  # write-only; stored as hashes


class HintBody(BaseModel):
    text: str | None = Field(None, min_length=1, max_length=2000)
    penalty: int | None = Field(None, ge=0, le=100000)
    position: int | None = Field(None, ge=1, le=99)


class DocumentBody(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=160)
    content: str | None = Field(None, min_length=1, max_length=20000)
    kind: Literal["genuine", "decoy"] | None = None
    stage: int | None = Field(None, ge=0, le=99)


class EncodeBody(BaseModel):
    cipher: Cipher
    text: str = Field(min_length=1, max_length=500)
    key: str = Field("", max_length=8000)


def _get(db: Session, model, item_id: int):
    item = db.get(model, item_id)
    if not item:
        raise HTTPException(404, f"{model.__name__} not found")
    return item


def _event(db: Session, event_id: int | None) -> Event:
    event = _get(db, Event, event_id) if event_id else active_event(db)
    if not event:
        raise HTTPException(404, "Create and activate an event first")
    return event


def _apply(item, body: BaseModel, fields: tuple[str, ...]) -> None:
    for name in fields:
        value = getattr(body, name)
        if value is not None:
            setattr(item, name, value)


def _hashes(answers: list[str]) -> list[str]:
    cleaned = [a for a in answers if normalize_answer(a)]
    if not cleaned:
        raise HTTPException(422, "Give at least one answer containing letters or digits")
    return sorted({answer_hash(a) for a in cleaned})


def _commit(db: Session, conflict: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, conflict)
    invalidate_leaderboard()


def event_out(e: Event) -> dict:
    return {
        "id": e.id, "name": e.name, "status": e.status, "is_active": e.is_active,
        "registration_open": e.registration_open, "wrong_penalty": e.wrong_penalty,
        "min_points": e.min_points, "final_message": e.final_message,
        "started_at": iso(e.started_at), "ended_at": iso(e.ended_at), "ends_at": iso(ends_at(e)),
        "team_size": e.team_size, "questions_per_team": e.questions_per_team or 0,
        "duration_minutes": e.duration_minutes or 0, "default_points": e.default_points,
        "hint_costs": e.hint_costs, "completion_bonus": e.completion_bonus,
        "map_provider": e.map_provider, "map_image_url": e.map_image_url,
        "map_lat": e.map_lat, "map_lng": e.map_lng, "map_zoom": e.map_zoom,
    }


def puzzle_out(p: Puzzle) -> dict:
    return {
        "id": p.id, "stage": p.stage, "title": p.title, "cipher": p.cipher, "prompt": p.prompt,
        "encoded_text": p.encoded_text, "points": p.points, "answer_count": len(p.answer_hashes),
        "hints": [{"id": h.id, "position": h.position, "text": h.text, "penalty": h.penalty} for h in p.hints],
    }


def document_out(d: Document) -> dict:
    return {"id": d.id, "title": d.title, "content": d.content, "kind": d.kind, "stage": d.stage}


EVENT_FIELDS = (
    "name", "registration_open", "wrong_penalty", "min_points", "final_message", "team_size",
    "default_points", "hint_costs", "completion_bonus", "map_provider", "map_image_url",
    "map_lat", "map_lng", "map_zoom",
)


def _apply_event(event: Event, body: EventBody) -> None:
    _apply(event, body, EVENT_FIELDS)
    if body.hint_costs is not None and any(c < 0 for c in body.hint_costs):
        raise HTTPException(422, "Hint costs cannot be negative")
    # For these two, 0 means "no limit" and is stored as NULL.
    if body.questions_per_team is not None:
        event.questions_per_team = body.questions_per_team or None
    if body.duration_minutes is not None:
        event.duration_minutes = body.duration_minutes or None


# ---- events ----

@router.get("/events")
def list_events(db: Session = Depends(get_db)):
    return [event_out(e) for e in db.scalars(select(Event).order_by(Event.id))]


@router.post("/events")
def create_event(body: EventBody, db: Session = Depends(get_db)):
    if not body.name:
        raise HTTPException(422, "An event needs a name")
    event = Event(name=body.name, is_active=active_event(db) is None)
    _apply_event(event, body)
    db.add(event)
    db.commit()
    return event_out(event)


@router.patch("/events/{event_id}")
def update_event(event_id: int, body: EventBody, db: Session = Depends(get_db)):
    event = _get(db, Event, event_id)
    _apply_event(event, body)
    if body.status and body.status != event.status:
        event.status = body.status
        if body.status == "live" and not event.started_at:
            event.started_at = utcnow()  # completion times are measured from the first go-live
        event.ended_at = utcnow() if body.status == "ended" else None
    db.commit()
    invalidate_leaderboard()
    return event_out(event)


@router.post("/events/{event_id}/activate")
def activate_event(event_id: int, db: Session = Depends(get_db)):
    event = _get(db, Event, event_id)
    db.execute(update(Event).values(is_active=False))
    event.is_active = True
    db.commit()
    invalidate_leaderboard()
    return event_out(event)


@router.delete("/events/{event_id}")
def delete_event(event_id: int, db: Session = Depends(get_db)):
    event = _get(db, Event, event_id)
    if event.is_active:
        raise HTTPException(409, "Activate another event before deleting this one")
    db.delete(event)
    db.commit()
    return {"ok": True}


# ---- teams and scores ----

@router.get("/teams")
def list_teams(event_id: int | None = None, db: Session = Depends(get_db)):
    return leaderboard(db, _event(db, event_id), include_disqualified=True)


@router.patch("/teams/{team_id}")
def update_team(team_id: int, body: TeamBody, db: Session = Depends(get_db)):
    team = _get(db, Team, team_id)
    if body.name:
        team.name = " ".join(body.name.split())
        team.name_key = team.name.lower()
    if body.score_delta:
        record_score(db, team, "adjust", body.score_delta, body.note or "Adjusted by an organiser")
    if body.disqualified is not None:
        team.disqualified = body.disqualified
    if body.new_password:
        team.password_hash = hash_password(body.new_password)
    _commit(db, "That team name is taken")
    return {"id": team.id, "name": team.name, "score": team.score, "disqualified": team.disqualified}


@router.post("/teams/{team_id}/reset")
def reset_team(team_id: int, db: Session = Depends(get_db)):
    team = _get(db, Team, team_id)
    for model in (Progress, Submission, ChatMessage, ScoreEvent):
        db.execute(delete(model).where(model.team_id == team.id))
    team.score, team.finished_at = 0, None
    _commit(db, "Could not reset the team")
    return {"ok": True}


@router.delete("/teams/{team_id}")
def delete_team(team_id: int, db: Session = Depends(get_db)):
    db.delete(_get(db, Team, team_id))
    _commit(db, "Could not delete the team")
    return {"ok": True}


@router.get("/submissions")
def recent_submissions(event_id: int | None = None, db: Session = Depends(get_db)):
    event = _event(db, event_id)
    rows = db.execute(
        select(Submission, Team.name, Puzzle.stage)
        .join(Team, Team.id == Submission.team_id).join(Puzzle, Puzzle.id == Submission.puzzle_id)
        .where(Team.event_id == event.id).order_by(Submission.id.desc()).limit(100)
    ).all()
    return [
        {"team": name, "stage": stage, "answer": s.answer, "correct": s.correct, "at": iso(s.created_at)}
        for s, name, stage in rows
    ]


@router.get("/overview")
def overview(event_id: int | None = None, db: Session = Depends(get_db)):
    event = _event(db, event_id)
    board = leaderboard(db, event, include_disqualified=True)
    chats = db.scalar(
        select(func.count()).select_from(ChatMessage).join(Team, Team.id == ChatMessage.team_id)
        .where(Team.event_id == event.id)
    )
    return {
        "event": event_out(event), "teams": len(board), "finished": sum(r["finished"] for r in board),
        "puzzles": db.scalar(select(func.count()).select_from(Puzzle).where(Puzzle.event_id == event.id)),
        "documents": db.scalar(select(func.count()).select_from(Document).where(Document.event_id == event.id)),
        "chat_messages": chats,
    }


def csv_response(filename: str, header: list[str], rows) -> Response:
    def cell(value):
        # A leading =, +, - or @ would run as a formula when the file is opened in a spreadsheet.
        text = "" if value is None else str(value)
        return "'" + text if text[:1] in ("=", "+", "-", "@") else text

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    for row in rows:
        writer.writerow([cell(v) for v in row])
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(out.getvalue(), media_type="text/csv", headers=headers)


@router.get("/export.csv")
def export_results(event_id: int | None = None, db: Session = Depends(get_db)):
    event = _event(db, event_id)
    header = [
        "rank", "team", "members", "score", "solved", "assigned", "finished", "elapsed_seconds",
        "finished_at", "wrong_attempts", "hints_used", "disqualified",
    ]
    rows = (
        (
            row["rank"], row["team"], "; ".join(row["members"]), row["score"], row["solved"], row["total"],
            "yes" if row["finished"] else "no", row["elapsed_seconds"], row["finished_at"],
            row["wrong_attempts"], row["hints_used"], "yes" if row["disqualified"] else "no",
        )
        for row in leaderboard(db, event, include_disqualified=True)
    )
    return csv_response(f"codehunt-results-{event.id}.csv", header, rows)


# ---- puzzles and hints ----

@router.get("/puzzles")
def list_puzzles(event_id: int | None = None, db: Session = Depends(get_db)):
    event = _event(db, event_id)
    return [puzzle_out(p) for p in db.scalars(select(Puzzle).where(Puzzle.event_id == event.id).order_by(Puzzle.stage))]


@router.post("/puzzles")
def create_puzzle(body: PuzzleBody, event_id: int | None = None, db: Session = Depends(get_db)):
    event = _event(db, event_id)
    if not (body.stage and body.title and body.cipher and body.answers):
        raise HTTPException(422, "A puzzle needs a stage, title, cipher and at least one answer")
    puzzle = Puzzle(event_id=event.id, points=event.default_points, answer_hashes=_hashes(body.answers))
    _apply(puzzle, body, ("stage", "title", "cipher", "prompt", "encoded_text", "points"))
    db.add(puzzle)
    _commit(db, f"Stage {body.stage} already exists")
    return puzzle_out(puzzle)


@router.patch("/puzzles/{puzzle_id}")
def update_puzzle(puzzle_id: int, body: PuzzleBody, db: Session = Depends(get_db)):
    puzzle = _get(db, Puzzle, puzzle_id)
    _apply(puzzle, body, ("stage", "title", "cipher", "prompt", "encoded_text", "points"))
    if body.answers:
        puzzle.answer_hashes = _hashes(body.answers)
    _commit(db, f"Stage {body.stage} already exists")
    return puzzle_out(puzzle)


@router.delete("/puzzles/{puzzle_id}")
def delete_puzzle(puzzle_id: int, db: Session = Depends(get_db)):
    db.delete(_get(db, Puzzle, puzzle_id))
    _commit(db, "Could not delete the puzzle")
    return {"ok": True}


@router.post("/puzzles/{puzzle_id}/hints")
def add_hint(puzzle_id: int, body: HintBody, db: Session = Depends(get_db)):
    puzzle = _get(db, Puzzle, puzzle_id)
    if not body.text:
        raise HTTPException(422, "A hint needs text")
    position = body.position or max((h.position for h in puzzle.hints), default=0) + 1
    penalty = body.penalty
    if penalty is None:  # fall back to the event's cost for a hint in this slot
        costs = _get(db, Event, puzzle.event_id).hint_costs or [10]
        penalty = costs[min(len(puzzle.hints), len(costs) - 1)]
    db.add(Hint(puzzle_id=puzzle.id, position=position, text=body.text, penalty=penalty))
    db.commit()
    db.refresh(puzzle)
    return puzzle_out(puzzle)


@router.patch("/hints/{hint_id}")
def update_hint(hint_id: int, body: HintBody, db: Session = Depends(get_db)):
    hint = _get(db, Hint, hint_id)
    _apply(hint, body, ("text", "penalty", "position"))
    db.commit()
    return {"ok": True}


@router.delete("/hints/{hint_id}")
def delete_hint(hint_id: int, db: Session = Depends(get_db)):
    db.delete(_get(db, Hint, hint_id))
    db.commit()
    return {"ok": True}


@router.post("/scoring/apply")
def apply_scoring_defaults(event_id: int | None = None, db: Session = Depends(get_db)):
    """Sets every question to the event's default points and every hint to the cost for its slot."""
    event = _event(db, event_id)
    costs = event.hint_costs or [10]
    puzzles = db.scalars(select(Puzzle).where(Puzzle.event_id == event.id)).all()
    for puzzle in puzzles:
        puzzle.points = event.default_points
        for slot, hint in enumerate(puzzle.hints):
            hint.penalty = costs[min(slot, len(costs) - 1)]
    db.commit()
    return {"puzzles": len(puzzles)}


@router.post("/encode")
def encode_text(body: EncodeBody):
    """Turns an answer into cipher text for a clue. Nothing is stored."""
    try:
        return {"encoded": ciphers.encode(body.cipher, body.text, body.key)}
    except ValueError as error:
        raise HTTPException(422, str(error))


# ---- knowledge base ----

@router.get("/documents")
def list_documents(event_id: int | None = None, db: Session = Depends(get_db)):
    event = _event(db, event_id)
    return [document_out(d) for d in db.scalars(select(Document).where(Document.event_id == event.id).order_by(Document.stage, Document.id))]


@router.post("/documents")
def create_document(body: DocumentBody, event_id: int | None = None, db: Session = Depends(get_db)):
    event = _event(db, event_id)
    if not (body.title and body.content):
        raise HTTPException(422, "A document needs a title and content")
    doc = Document(event_id=event.id, title=body.title, content=body.content, kind=body.kind or "genuine", stage=body.stage or 0)
    db.add(doc)
    db.flush()
    rag.index_document(db, doc)
    db.commit()
    return document_out(doc)


@router.patch("/documents/{doc_id}")
def update_document(doc_id: int, body: DocumentBody, db: Session = Depends(get_db)):
    doc = _get(db, Document, doc_id)
    _apply(doc, body, ("title", "content", "kind", "stage"))
    rag.index_document(db, doc)
    db.commit()
    return document_out(doc)


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    db.delete(_get(db, Document, doc_id))
    db.commit()
    return {"ok": True}


@router.post("/documents/reindex")
def reindex_documents(event_id: int | None = None, db: Session = Depends(get_db)):
    """Re-embed everything, for example after switching embedding provider."""
    event = _event(db, event_id)
    docs = db.scalars(select(Document).where(Document.event_id == event.id)).all()
    chunks = sum(rag.index_document(db, doc) for doc in docs)
    db.commit()
    return {"documents": len(docs), "chunks": chunks}
