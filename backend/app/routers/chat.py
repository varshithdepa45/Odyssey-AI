"""The Oracle: the dashboard chatbot. Explains rules and techniques from the archive (RAG), points to
the next permitted step, and offers hints. It never holds an answer, and every reply is checked by
app.guard before it is sent."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import guard, rag
from ..config import get_settings
from ..db import get_db, utcnow
from ..models import ChatMessage, Puzzle, Team
from ..security import current_team, limiter
from ..service import (
    current_puzzle, next_step, progress_for, reached_stages, require_event, require_live,
    rules_summary, split_markers, team_puzzles,
)
from .game import next_hint

settings = get_settings()
router = APIRouter(prefix="/api", tags=["chat"])


class ChatBody(BaseModel):
    message: str = Field(min_length=2, max_length=500)


def chat_remaining(db: Session, team_id: int) -> int:
    since = utcnow() - timedelta(hours=24)
    used = db.scalar(
        select(func.count()).select_from(ChatMessage).where(
            ChatMessage.team_id == team_id, ChatMessage.created_at >= since, ChatMessage.kind != "hint"
        )
    )
    return max(settings.chat_daily_limit - used, 0)


@router.post("/chat")
def chat(body: ChatBody, team: Team = Depends(current_team), db: Session = Depends(get_db)):
    limiter.check(f"chat:{team.id}", settings.chat_per_minute)
    event = require_event(db)
    require_live(event)
    remaining = chat_remaining(db, team.id)
    if remaining <= 0:
        raise HTTPException(429, "Your team has used all of today's Oracle questions")
    question = guard.sanitize(body.message)
    if len(question) < 2:
        raise HTTPException(422, "Ask a question in plain text")

    puzzles = team_puzzles(db, event, team.id)
    progress = progress_for(db, team.id)
    puzzle = current_puzzle(puzzles, progress)
    position = puzzles.index(puzzle) + 1 if puzzle else 0
    entry = progress.get(puzzle.id) if puzzle else None
    offer, sources, kind = None, [], "chat"

    if guard.is_injection(question):
        answer, mode, kind = guard.BLOCKED_REPLY, "blocked", "blocked"
    elif guard.wants_hint(question):
        offer = next_hint(event, puzzle, entry) if puzzle else None
        mode = "hint_offer"
        if offer:
            answer = (
                f"Hint {offer['number']} of {offer['total']} is ready for question {position}. It costs "
                f"{offer['cost']} points, taken only if the hint is delivered. Confirm below to reveal it."
            )
        elif puzzle:
            answer = "Every hint for this question has been released. Ask me how the cipher works instead."
        else:
            answer = "There is no open question to give a hint for."
    else:
        # What must not appear in a reply: answers to questions this team has not solved, and the
        # names of map markers it has not unlocked.
        solved_ids = {pid for pid, e in progress.items() if e.solved_at}
        protected = {
            h for p in db.scalars(select(Puzzle).where(Puzzle.event_id == event.id))
            if p.id not in solved_ids for h in p.answer_hashes
        }
        visible, hidden = split_markers(db, event, team)
        hidden_names = [m.name for m in hidden]

        reached, _ = reached_stages(event, puzzles, progress)
        stages = None if team.finished_at else reached
        passages = [
            p for p in rag.retrieve(db, event.id, stages, question)
            if not guard.leaks(p["content"], protected, hidden_names)
        ]
        if guard.asks_navigation(question):
            passages.insert(0, {"title": "Your Next Step", "content": next_step(event, team, puzzle, position, visible)})
        if guard.asks_rules(question):
            passages.insert(0, {"title": "Hunt Rules", "content": rules_summary(event)})

        note = ""
        if puzzle:
            released = "; ".join(h.text for h in puzzle.hints[: entry.hints_used]) if entry else ""
            note = (
                f"This team is on question {position} of {len(puzzles)}, a {puzzle.cipher} cipher. "
                f"Hints already released to them: {released or 'none'}."
            )
        answer, mode = rag.answer_question(question, passages, note)
        sources = list(dict.fromkeys(p["title"] for p in passages))
        if mode == "ai" and guard.leaks(answer, protected, hidden_names, question):
            answer, mode, kind, sources = guard.LEAK_REPLY, "blocked", "blocked", []

    db.add(ChatMessage(team_id=team.id, kind=kind, question=question, answer=answer))
    db.commit()
    return {"answer": answer, "mode": mode, "sources": sources, "remaining": remaining - 1, "hint_offer": offer}


@router.get("/chat/history")
def chat_history(team: Team = Depends(current_team), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(ChatMessage).where(ChatMessage.team_id == team.id).order_by(ChatMessage.id.desc()).limit(30)
    ).all()
    return {
        "messages": [{"kind": m.kind, "question": m.question, "answer": m.answer} for m in reversed(rows)],
        "remaining": chat_remaining(db, team.id),
    }
