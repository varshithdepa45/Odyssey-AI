import hashlib
import hmac
import os
import time
import unicodedata
from collections import defaultdict, deque
from datetime import timedelta
from threading import Lock

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db, utcnow
from .models import Team

settings = get_settings()
bearer = HTTPBearer(auto_error=False)
PBKDF2_ROUNDS = 200_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2${PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, rounds, salt, digest = stored.split("$")
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
    except ValueError:
        return False
    return hmac.compare_digest(candidate.hex(), digest)


def normalize_answer(raw: str) -> str:
    """Uppercase and keep only letters and digits, so spacing and punctuation never matter."""
    text = unicodedata.normalize("NFKD", raw).upper()
    return "".join(ch for ch in text if ch.isascii() and ch.isalnum())


def answer_hash(raw: str) -> str:
    return hmac.new(settings.answer_pepper.encode(), normalize_answer(raw).encode(), hashlib.sha256).hexdigest()


def answer_matches(raw: str, hashes: list[str]) -> bool:
    candidate = answer_hash(raw)
    return any(hmac.compare_digest(candidate, h) for h in hashes)


def make_token(subject: str, role: str) -> str:
    payload = {"sub": subject, "role": role, "exp": utcnow() + timedelta(hours=settings.token_hours)}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def _claims(creds: HTTPAuthorizationCredentials | None) -> dict:
    if not creds:
        raise HTTPException(401, "Sign in required")
    try:
        return jwt.decode(creds.credentials, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Session expired, sign in again")


def current_team(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> Team:
    claims = _claims(creds)
    if claims.get("role") != "team":
        raise HTTPException(403, "Team account required")
    team = db.get(Team, int(claims["sub"]))
    if not team:
        raise HTTPException(401, "Team no longer exists")
    if team.disqualified:
        raise HTTPException(403, "This team has been disqualified")
    return team


def current_admin(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    claims = _claims(creds)
    if claims.get("role") != "admin":
        raise HTTPException(403, "Admin access required")
    return claims["sub"]


class RateLimiter:
    """Sliding window, in memory. Fine for one backend instance, which is what the free tiers give you."""

    def __init__(self):
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, limit: int, window: int = 60) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > window:
                hits.popleft()
            if len(hits) >= limit:
                retry = int(window - (now - hits[0])) + 1
                raise HTTPException(
                    429, f"Too many requests. Try again in {retry}s.", headers={"Retry-After": str(retry)}
                )
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    if settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def limit_by_ip(bucket: str, limit: int):
    def dependency(request: Request) -> None:
        limiter.check(f"{bucket}:{client_ip(request)}", limit)

    return dependency
