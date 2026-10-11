import os
import tempfile

# Settings are read at import time, so the test environment is set before the app is imported.
_db = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ.update(
    DATABASE_URL=os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_db}"),
    ENV="development", AI_PROVIDER="none", EMBEDDING_PROVIDER="hash", AUTO_SEED="false",
    SECRET_KEY="test-secret-key-that-is-long-enough-for-hs256", ANSWER_PEPPER="test-pepper",
    ADMIN_USERNAME="admin", ADMIN_PASSWORD="admin-pass", SUBMIT_PER_MINUTE="1000",
    CHAT_PER_MINUTE="1000", LOGIN_PER_MINUTE="1000", REGISTER_PER_MINUTE="1000",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.security import limiter  # noqa: E402
from app.seed import PUZZLES, seed  # noqa: E402
from app.service import invalidate_leaderboard  # noqa: E402

ANSWERS = {stage: answer for stage, _, _, answer, _ in PUZZLES}


@pytest.fixture()
def client():
    """A fresh seeded database with the event live."""
    Base.metadata.drop_all(engine)
    init_db()
    limiter.reset()
    invalidate_leaderboard()
    with SessionLocal() as db:
        seed(db)
    with TestClient(app) as test_client:
        admin = admin_headers(test_client)
        event_id = test_client.get("/api/admin/events", headers=admin).json()[0]["id"]
        test_client.patch(f"/api/admin/events/{event_id}", json={"status": "live"}, headers=admin)
        yield test_client


def admin_headers(client) -> dict:
    token = client.post("/api/auth/admin", json={"username": "admin", "password": "admin-pass"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def register(client, name="Team Rocket", password="hunter22") -> dict:
    response = client.post("/api/auth/register", json={"team_name": name, "password": password, "members": ["A", "B"]})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}
