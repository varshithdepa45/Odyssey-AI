from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db, iso, utcnow
from ..models import ChatMessage, Event, Progress, Puzzle, ScoreEvent, Submission, Team
from ..security import answer_matches, client_ip, current_team, limiter
from ..service import (
    TIE_BREAKS, charge, current_puzzle, ends_at, event_puzzles, leaderboard, net_value, penalty_room,
    progress_for, question_leaderboard, record_score, require_event, require_live, team_puzzles,
)

settings = get_settings()
router = APIRouter(prefix="/api", tags=["game"])


class AnswerBody(BaseModel):
    answer: str = Field(min_length=1, max_length=200)
    # The question the player was looking at. If it has been solved in the meantime (a double click,
    # a teammate's device), the submission is turned away instead of being judged against the next one.
    stage: int | None = Field(None, ge=1, le=99)


class HintBody(BaseModel):
    # Which hint the player confirmed. Sending it makes a retried request safe: asking again for a
    # hint that was already delivered returns it without a second charge.
    number: int | None = Field(None, ge=1, le=99)


def lock_team(db: Session, team: Team) -> Team:
    """Serialises everything that changes one team's score, so simultaneous requests cannot both count."""
    return db.scalars(
        select(Team).where(Team.id == team.id).with_for_update().execution_options(populate_existing=True)
    ).one()


def get_entry(db: Session, progress: dict, team_id: int, puzzle_id: int) -> Progress:
    entry = progress.get(puzzle_id)
    if not entry:
        entry = Progress(
            team_id=team_id, puzzle_id=puzzle_id, wrong_attempts=0, hints_used=0, penalty_total=0, points_awarded=0
        )
        db.add(entry)
    return entry


def next_hint(event: Event, puzzle: Puzzle, entry: Progress | None) -> dict | None:
    used = entry.hints_used if entry else 0
    if used >= len(puzzle.hints):
        return None
    room = penalty_room(event, puzzle, entry) if entry else puzzle.points - min(event.min_points, puzzle.points)
    return {"number": used + 1, "cost": min(puzzle.hints[used].penalty, max(room, 0)), "total": len(puzzle.hints)}


@router.get("/event")
def public_event(db: Session = Depends(get_db)):
    """What the sign-up form needs to know. Nothing about questions or the map."""
    event = require_event(db)
    return {
        "name": event.name, "status": event.status, "team_size": event.team_size,
        "registration_open": event.registration_open and event.status != "ended",
    }


@router.get("/game")
def game_state(team: Team = Depends(current_team), db: Session = Depends(get_db)):
    """Everything the dashboard needs. Locked questions carry no content, and nothing carries an answer."""
    event = require_event(db)
    puzzles = team_puzzles(db, event, team.id)
    progress = progress_for(db, team.id)
    current = current_puzzle(puzzles, progress)
    stages = []
    for position, puzzle in enumerate(puzzles, 1):
        entry = progress.get(puzzle.id)
        solved = bool(entry and entry.solved_at)
        status = "solved" if solved else "current" if current and puzzle.id == current.id else "locked"
        stage = {"stage": position, "status": status}
        if status != "locked" and event.status != "draft":
            used = entry.hints_used if entry else 0
            stage.update(
                question=puzzle.stage, title=puzzle.title, cipher=puzzle.cipher, prompt=puzzle.prompt,
                encoded_text=puzzle.encoded_text, points=puzzle.points,
                wrong_attempts=entry.wrong_attempts if entry else 0,
                hints=[{"number": i, "text": h.text, "penalty": h.penalty} for i, h in enumerate(puzzle.hints[:used], 1)],
                hints_total=len(puzzle.hints),
                next_hint=None if solved else next_hint(event, puzzle, entry),
                points_awarded=entry.points_awarded if solved else None,
                potential_points=None if solved else net_value(puzzle, entry),
                solved_at=iso(entry.solved_at) if solved else None,
            )
        stages.append(stage)
    finished = team.finished_at is not None
    return {
        "event": {
            "name": event.name, "status": event.status, "started_at": iso(event.started_at),
            "ends_at": iso(ends_at(event)), "wrong_penalty": event.wrong_penalty,
            "completion_bonus": event.completion_bonus, "min_points": event.min_points,
        },
        "team": {"name": team.name, "members": team.members, "score": team.score, "finished_at": iso(team.finished_at)},
        "stages": stages,
        "final_message": event.final_message if finished else None,
    }


@router.post("/game/submit")
def submit_answer(body: AnswerBody, team: Team = Depends(current_team), db: Session = Depends(get_db)):
    limiter.check(f"submit:{team.id}", settings.submit_per_minute)
    event = require_event(db)
    require_live(event)
    team = lock_team(db, team)
    puzzles = team_puzzles(db, event, team.id)
    progress = progress_for(db, team.id)
    puzzle = current_puzzle(puzzles, progress)
    if not puzzle:
        raise HTTPException(409, "Your team has already finished the hunt" if puzzles else "No questions are assigned to your team yet")
    position = puzzles.index(puzzle) + 1
    if body.stage and body.stage != position:
        raise HTTPException(409, f"Question {body.stage} is already solved. You are on question {position}.")
    entry = get_entry(db, progress, team.id, puzzle.id)
    correct = answer_matches(body.answer, puzzle.answer_hashes)
    # Wrong guesses are kept for organisers to review; correct ones are not written down anywhere.
    db.add(Submission(team_id=team.id, puzzle_id=puzzle.id, answer="" if correct else body.answer, correct=correct))

    if not correct:
        entry.wrong_attempts += 1
        taken = 0
        if penalty_room(event, puzzle, entry) > 0 and event.wrong_penalty:
            taken = charge(db, event, team, puzzle, entry, "wrong", event.wrong_penalty, f"Wrong answer on question {puzzle.stage}")
        db.commit()
        return {
            "correct": False, "score": team.score, "finished": False, "penalty": taken,
            "message": f"Not it. {taken} points deducted." if taken else "Not it. Check the cipher and try again.",
            "potential_points": net_value(puzzle, entry),
        }

    now = utcnow()
    entry.solved_at = now
    entry.points_awarded = net_value(puzzle, entry)
    record_score(db, team, "correct", puzzle.points, f"Solved question {puzzle.stage}", puzzle, f"correct:{team.id}:{puzzle.id}")
    finished = puzzle.id == puzzles[-1].id
    bonus = 0
    if finished:
        team.finished_at = now
        bonus = event.completion_bonus
        if bonus:
            record_score(db, team, "bonus", bonus, "Completed every question", dedupe_key=f"bonus:{team.id}")
    try:
        db.commit()
    except IntegrityError:  # the same solve arrived twice; the first one already counted
        db.rollback()
        raise HTTPException(409, "That answer was already recorded")
    message = f"Question {position} cleared. Next one unlocked."
    if finished:
        message = "Hunt complete!" + (f" +{bonus} completion bonus." if bonus else "")
    return {
        "correct": True, "score": team.score, "finished": finished, "points_awarded": puzzle.points,
        "net_points": entry.points_awarded, "bonus": bonus, "message": message,
    }


@router.post("/game/hint")
def reveal_hint(body: HintBody | None = None, team: Team = Depends(current_team), db: Session = Depends(get_db)):
    """Delivers the next hint and charges for it in one transaction: no delivery, no charge, and never twice."""
    limiter.check(f"hint:{team.id}", 10)
    event = require_event(db)
    require_live(event)
    team = lock_team(db, team)
    puzzles = team_puzzles(db, event, team.id)
    progress = progress_for(db, team.id)
    puzzle = current_puzzle(puzzles, progress)
    if not puzzle:
        raise HTTPException(409, "There is no open question to give a hint for")
    entry = get_entry(db, progress, team.id, puzzle.id)
    number = body.number if body and body.number else entry.hints_used + 1

    def delivered(charged: int, repeat: bool) -> dict:
        hint = puzzle.hints[number - 1]
        return {
            "hint": {"number": number, "text": hint.text, "penalty": hint.penalty},
            "charged": charged, "already_revealed": repeat, "score": team.score,
            "potential_points": net_value(puzzle, entry), "next_hint": next_hint(event, puzzle, entry),
        }

    if number <= entry.hints_used:
        return delivered(0, True)
    if number > len(puzzle.hints):
        raise HTTPException(404, "No more hints for this question")
    if number != entry.hints_used + 1:
        raise HTTPException(409, f"Hints come in order. Hint {entry.hints_used + 1} is next.")
    hint = puzzle.hints[number - 1]
    entry.hints_used = number
    taken = charge(
        db, event, team, puzzle, entry, "hint", hint.penalty,
        f"Hint {number} on question {puzzle.stage}", f"hint:{team.id}:{puzzle.id}:{number}",
    )
    db.add(ChatMessage(team_id=team.id, kind="hint", question=f"Hint {number} requested", answer=hint.text))
    try:
        db.commit()
    except IntegrityError:  # a duplicate of this request won the race; return what it delivered
        db.rollback()
        team = db.get(Team, team.id)
        entry = progress_for(db, team.id)[puzzle.id]
        return delivered(0, True)
    return delivered(taken, False)


@router.get("/game/history")
def score_history(team: Team = Depends(current_team), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(ScoreEvent).where(ScoreEvent.team_id == team.id).order_by(ScoreEvent.id.desc()).limit(100)
    ).all()
    return {
        "score": team.score,
        "events": [{"kind": r.kind, "delta": r.delta, "note": r.note, "at": iso(r.created_at)} for r in rows],
    }


@router.get("/leaderboard")
def public_leaderboard(request: Request, db: Session = Depends(get_db)):
    limiter.check(f"board:{client_ip(request)}", 60)
    event = require_event(db)
    public = ("rank", "team", "score", "solved", "total", "hints_used", "finished", "elapsed_seconds")
    return {
        "event": {"name": event.name, "status": event.status, "ends_at": iso(ends_at(event))},
        "questions": [p.stage for p in event_puzzles(db, event.id)],
        "tie_breaks": TIE_BREAKS,
        "rows": [{k: row[k] for k in public} for row in leaderboard(db, event)],
    }


@router.get("/leaderboard/question/{number}")
def public_question_leaderboard(number: int, request: Request, db: Session = Depends(get_db)):
    limiter.check(f"board:{client_ip(request)}", 60)
    event = require_event(db)
    puzzle = db.scalars(select(Puzzle).where(Puzzle.event_id == event.id, Puzzle.stage == number)).first()
    if not puzzle:
        raise HTTPException(404, "No such question")
    return {
        "question": number,
        "tie_breaks": "Solved first, then points kept, then earlier solve, then fewer hints.",
        "rows": question_leaderboard(db, event, puzzle),
    }
