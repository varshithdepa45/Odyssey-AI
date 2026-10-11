import hmac

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Participant, Team
from ..security import current_team, hash_password, limit_by_ip, make_token, verify_password
from ..service import invalidate_leaderboard, require_event, sync_members

settings = get_settings()
router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterBody(BaseModel):
    team_name: str = Field(min_length=2, max_length=40)
    password: str = Field(min_length=6, max_length=128)
    members: list[str] = Field(default_factory=list, max_length=50)  # the event's team size is checked below

    @field_validator("team_name")
    @classmethod
    def tidy_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2:
            raise ValueError("Team name is too short")
        return value

    @field_validator("members")
    @classmethod
    def tidy_members(cls, value: list[str]) -> list[str]:
        return [m.strip()[:60] for m in value if m.strip()]


class LoginBody(BaseModel):
    team_name: str = Field(max_length=40)
    password: str = Field(max_length=128)


class AdminLoginBody(BaseModel):
    username: str = Field(max_length=80)
    password: str = Field(max_length=128)


def team_out(team: Team) -> dict:
    return {"id": team.id, "name": team.name, "members": team.members, "score": team.score}


@router.post("/register", dependencies=[Depends(limit_by_ip("register", settings.register_per_minute))])
def register(body: RegisterBody, db: Session = Depends(get_db)):
    event = require_event(db)
    if not event.registration_open or event.status == "ended":
        raise HTTPException(403, "Registration is closed")
    members = body.members or ([body.team_name] if event.team_size == 1 else [])
    if len(members) > event.team_size:
        limit = "one participant" if event.team_size == 1 else f"{event.team_size} members"
        raise HTTPException(422, f"This event allows {limit} per team")
    team = Team(
        event_id=event.id, name=body.team_name, name_key=body.team_name.lower(),
        password_hash=hash_password(body.password), members=[],
    )
    db.add(team)
    try:
        db.flush()
        for name in members:
            db.add(Participant(event_id=event.id, team_id=team.id, name=name))
        sync_members(db, team)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "That team name is taken")
    invalidate_leaderboard()
    return {"token": make_token(str(team.id), "team"), "team": team_out(team)}


@router.post("/login", dependencies=[Depends(limit_by_ip("login", settings.login_per_minute))])
def login(body: LoginBody, db: Session = Depends(get_db)):
    event = require_event(db)
    name_key = " ".join(body.team_name.split()).lower()
    team = db.scalars(select(Team).where(Team.event_id == event.id, Team.name_key == name_key)).first()
    if not team or not verify_password(body.password, team.password_hash):
        raise HTTPException(401, "Wrong team name or password")
    if team.disqualified:
        raise HTTPException(403, "This team has been disqualified")
    return {"token": make_token(str(team.id), "team"), "team": team_out(team)}


@router.post("/admin", dependencies=[Depends(limit_by_ip("admin-login", settings.login_per_minute))])
def admin_login(body: AdminLoginBody):
    user_ok = hmac.compare_digest(body.username.encode(), settings.admin_username.encode())
    pass_ok = hmac.compare_digest(body.password.encode(), settings.admin_password.encode())
    if not (user_ok and pass_ok):
        raise HTTPException(401, "Wrong admin credentials")
    return {"token": make_token(settings.admin_username, "admin")}


@router.get("/me")
def me(team: Team = Depends(current_team)):
    return team_out(team)
