import json

from app import ciphers, rag
from app.security import limiter
from app.seed import BOOK_PASSAGE, VIGENERE_KEY

from .conftest import ANSWERS, admin_headers, register


def solve_all(client, headers):
    for stage in range(1, 10):
        result = client.post("/api/game/submit", json={"answer": ANSWERS[stage]}, headers=headers).json()
        assert result["correct"], (stage, result)
    return result


# ---- ciphers ----

def test_cipher_vectors():
    assert ciphers.encode("binary", "Hi") == "01001000 01001001"
    assert ciphers.encode("morse", "sos now") == "... --- ... / -. --- .--"
    assert ciphers.encode("caesar", "XYZ", "3") == "ABC"
    assert ciphers.encode("polybius", "FJ") == "21 24"
    assert ciphers.encode("vigenere", "ATTACK AT DAWN", "LEMON") == "LXFOPV EF RNHR"
    assert ciphers.encode("hex", "AZ") == "41 5A"
    assert ciphers.encode("braille", "abc") == "⠁⠃⠉"
    assert ciphers.encode("ascii", "A Z") == "65 32 90"


def test_book_cipher_round_trip():
    lines = [line.split() for line in BOOK_PASSAGE.splitlines()]
    encoded = ciphers.encode("book", "QUANTUM LANTERN", BOOK_PASSAGE)
    decoded = " ".join(
        "".join(
            "".join(c for c in lines[l - 1][w - 1] if c.isalpha())[c_ - 1].upper()
            for l, w, c_ in (map(int, ref.split(".")) for ref in word.split())
        )
        for word in encoded.split(" / ")
    )
    assert decoded == "QUANTUM LANTERN"


# ---- auth ----

def test_register_login_and_duplicates(client):
    register(client, "Alpha")
    assert client.post("/api/auth/register", json={"team_name": "alpha", "password": "another1"}).status_code == 409
    assert client.post("/api/auth/login", json={"team_name": "ALPHA", "password": "hunter22"}).status_code == 200
    assert client.post("/api/auth/login", json={"team_name": "Alpha", "password": "wrong-pass"}).status_code == 401
    assert client.post("/api/auth/register", json={"team_name": "Beta", "password": "123"}).status_code == 422


def test_protected_routes_need_the_right_token(client):
    team = register(client)
    assert client.get("/api/game").status_code == 401
    assert client.get("/api/admin/teams").status_code == 401
    assert client.get("/api/admin/teams", headers=team).status_code == 403
    assert client.get("/api/game", headers=admin_headers(client)).status_code == 403
    assert client.get("/api/game", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_login_is_rate_limited(client, monkeypatch):
    limiter.reset()
    codes = set()
    for _ in range(1005):
        codes.add(client.post("/api/auth/login", json={"team_name": "nobody", "password": "x"}).status_code)
    assert codes == {401, 429}


# ---- game ----

def test_game_state_hides_locked_stages_and_answers(client):
    team = register(client)
    state = client.get("/api/game", headers=team)
    stages = state.json()["stages"]
    assert [s["status"] for s in stages] == ["current"] + ["locked"] * 8
    assert stages[0]["encoded_text"] and stages[0]["cipher"] == "binary"
    assert all(set(s) == {"stage", "status"} for s in stages[1:])
    body = state.text.upper()
    assert "ANSWER_HASH" not in body
    assert not any(answer in body for answer in ANSWERS.values())
    assert state.json()["final_message"] is None


def test_scoring_with_wrong_answers_and_hints(client):
    team = register(client)
    wrong = client.post("/api/game/submit", json={"answer": "nope"}, headers=team).json()
    assert wrong == {**wrong, "correct": False, "potential_points": 95}
    hint = client.post("/api/game/hint", headers=team).json()
    assert hint["hint"]["penalty"] == 10 and hint["potential_points"] == 85
    # Case, spacing and punctuation are ignored.
    right = client.post("/api/game/submit", json={"answer": " copper-falcon! "}, headers=team).json()
    assert right["correct"] and right["net_points"] == 85 and right["score"] == 85
    stages = client.get("/api/game", headers=team).json()["stages"]
    assert [s["status"] for s in stages[:3]] == ["solved", "current", "locked"]
    assert stages[0]["hints"][0]["text"]


def test_points_never_drop_below_the_floor(client):
    team = register(client)
    for _ in range(30):
        client.post("/api/game/submit", json={"answer": "wrong"}, headers=team)
    right = client.post("/api/game/submit", json={"answer": ANSWERS[1]}, headers=team).json()
    assert right["net_points"] == 20 and right["score"] == 20


def test_cannot_skip_ahead(client):
    team = register(client)
    skipped = client.post("/api/game/submit", json={"answer": ANSWERS[2]}, headers=team).json()
    assert skipped["correct"] is False


def test_completion_reveals_the_final_message(client):
    team = register(client)
    assert solve_all(client, team)["finished"] is True
    state = client.get("/api/game", headers=team).json()
    assert state["final_message"] and state["team"]["finished_at"]
    assert client.post("/api/game/submit", json={"answer": "again"}, headers=team).status_code == 409


def test_play_is_blocked_unless_live(client):
    team = register(client)
    admin = admin_headers(client)
    event_id = client.get("/api/admin/events", headers=admin).json()[0]["id"]
    client.patch(f"/api/admin/events/{event_id}", json={"status": "paused"}, headers=admin)
    assert client.post("/api/game/submit", json={"answer": ANSWERS[1]}, headers=team).status_code == 409
    assert client.post("/api/game/hint", headers=team).status_code == 409
    assert client.post("/api/chat", json={"message": "caesar shift"}, headers=team).status_code == 409
    client.patch(f"/api/admin/events/{event_id}", json={"status": "draft"}, headers=admin)
    stages = client.get("/api/game", headers=team).json()["stages"]
    assert all("encoded_text" not in s for s in stages)


# ---- leaderboard ----

def test_leaderboard_ranks_by_score_then_completion(client):
    slow, fast, partial = register(client, "Slow"), register(client, "Fast"), register(client, "Partial")
    client.post("/api/game/submit", json={"answer": "wrong"}, headers=slow)  # Slow loses 5 points
    solve_all(client, fast)
    solve_all(client, slow)
    client.post("/api/game/submit", json={"answer": ANSWERS[1]}, headers=partial)
    board = client.get("/api/leaderboard").json()
    assert [(r["rank"], r["team"], r["score"]) for r in board["rows"]] == [
        (1, "Fast", 1000), (2, "Slow", 995), (3, "Partial", 100),
    ]
    assert board["rows"][0]["finished"] and board["rows"][0]["elapsed_seconds"] is not None
    assert board["rows"][0]["total"] == 9 and board["questions"] == list(range(1, 10))
    assert "members" not in board["rows"][0]


def test_same_score_is_broken_by_who_finished_first(client):
    first, second = register(client, "First"), register(client, "Second")
    solve_all(client, first)
    solve_all(client, second)
    assert [r["team"] for r in client.get("/api/leaderboard").json()["rows"]] == ["First", "Second"]


# ---- RAG ----

def test_hash_embeddings_rank_related_text_higher():
    query = rag.hash_embed("what is the vigenere keyword", 384)
    related = rag.hash_embed("The committee's Vigenere keyword for this season", 384)
    unrelated = rag.hash_embed("Braille writes each letter as raised dots", 384)
    assert rag._cosine(query, related) > rag._cosine(query, unrelated) + 0.1


def test_chunking_keeps_all_content():
    text = "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(6))
    chunks = rag.chunk_text(text, max_chars=700)
    assert len(chunks) > 1 and all(len(c) <= 700 for c in chunks)
    assert all(f"Paragraph {i} " in "".join(chunks) for i in range(6))


def test_chat_retrieves_only_unlocked_documents(client):
    team = register(client)
    early = client.post("/api/chat", json={"message": "What is the Vigenere keyword this season?"}, headers=team).json()
    assert VIGENERE_KEY not in early["answer"]
    assert not any("Vigenere" in title for title in early["sources"])
    for stage in range(1, 5):
        client.post("/api/game/submit", json={"answer": ANSWERS[stage]}, headers=team)
    later = client.post("/api/chat", json={"message": "What is the Vigenere keyword this season?"}, headers=team).json()
    assert later["mode"] == "excerpts"
    assert later["sources"][0] in ("Field Notes: The Vigenere Lock", "Overheard: The Frost Keyword")
    # Genuine record and decoy both surface; telling them apart is the players' job.
    assert VIGENERE_KEY in later["answer"] and "FROST" in later["answer"]
    assert later["remaining"] == 78


def test_chat_passes_retrieved_passages_to_the_model(client, monkeypatch):
    team = register(client)
    seen = {}

    def fake_model(prompt):
        seen["prompt"] = prompt
        return "Eight bits per character [Field Notes: Binary]."

    monkeypatch.setattr(rag.settings, "ai_provider", "openai_compatible")
    monkeypatch.setattr(rag, "_ask_openai_compatible", fake_model)
    reply = client.post("/api/chat", json={"message": "How do I read binary?"}, headers=team).json()
    assert reply["mode"] == "ai" and reply["answer"].startswith("Eight bits")
    assert "Field Notes: Binary" in seen["prompt"] and "How do I read binary?" in seen["prompt"]
    assert not any(answer in seen["prompt"].upper() for answer in ANSWERS.values())


def test_chat_falls_back_to_excerpts_when_the_model_fails(client, monkeypatch):
    team = register(client)

    def broken(_prompt):
        raise RuntimeError("provider down")

    monkeypatch.setattr(rag.settings, "ai_provider", "openai_compatible")
    monkeypatch.setattr(rag, "_ask_openai_compatible", broken)
    reply = client.post("/api/chat", json={"message": "How do I read binary?"}, headers=team).json()
    assert reply["mode"] == "excerpts" and "eight bits" in reply["answer"].lower()


def test_chat_daily_limit(client, monkeypatch):
    team = register(client)
    monkeypatch.setattr("app.routers.game.settings.chat_daily_limit", 2)
    for _ in range(2):
        assert client.post("/api/chat", json={"message": "binary help"}, headers=team).status_code == 200
    assert client.post("/api/chat", json={"message": "binary help"}, headers=team).status_code == 429


# ---- admin ----

def test_admin_manages_puzzles_without_seeing_answers(client):
    admin = admin_headers(client)
    puzzles = client.get("/api/admin/puzzles", headers=admin)
    assert len(puzzles.json()) == 9 and "answer_hashes" not in puzzles.text
    first = puzzles.json()[0]
    encoded = client.post("/api/admin/encode", json={"cipher": "caesar", "text": "new answer", "key": "1"}, headers=admin).json()
    assert encoded["encoded"] == "OFX BOTXFS"
    patch = {"answers": ["New Answer", "alt answer"], "encoded_text": encoded["encoded"], "points": 50}
    updated = client.patch(f"/api/admin/puzzles/{first['id']}", json=patch, headers=admin).json()
    assert updated["answer_count"] == 2 and updated["points"] == 50

    team = register(client)
    assert client.post("/api/game/submit", json={"answer": ANSWERS[1]}, headers=team).json()["correct"] is False
    assert client.post("/api/game/submit", json={"answer": "ALT-ANSWER"}, headers=team).json()["net_points"] == 45

    added = client.post(f"/api/admin/puzzles/{first['id']}/hints", json={"text": "Third hint", "penalty": 40}, headers=admin).json()
    assert [h["position"] for h in added["hints"]] == [1, 2, 3, 4]
    assert client.delete(f"/api/admin/hints/{added['hints'][3]['id']}", headers=admin).status_code == 200
    assert client.post("/api/admin/puzzles", json={"stage": 1, "title": "Dup", "cipher": "hex", "answers": ["x"]}, headers=admin).status_code == 409


def test_admin_documents_are_indexed_for_search(client):
    admin, team = admin_headers(client), register(client)
    doc = client.post("/api/admin/documents", json={
        "title": "Field Notes: Semaphore", "content": "Semaphore signals letters with two flags held at angles.",
        "kind": "genuine", "stage": 0,
    }, headers=admin).json()
    reply = client.post("/api/chat", json={"message": "How does semaphore signal letters?"}, headers=team).json()
    assert reply["sources"][0] == "Field Notes: Semaphore"
    client.patch(f"/api/admin/documents/{doc['id']}", json={"stage": 9}, headers=admin)
    hidden = client.post("/api/chat", json={"message": "How does semaphore signal letters?"}, headers=team).json()
    assert "Field Notes: Semaphore" not in hidden["sources"]
    assert client.delete(f"/api/admin/documents/{doc['id']}", headers=admin).status_code == 200
    assert client.post("/api/admin/documents/reindex", headers=admin).json()["documents"] == 17


def test_admin_team_controls_and_csv_export(client):
    admin = admin_headers(client)
    good, bad = register(client, "Good"), register(client, "=SUM(A1)")
    client.post("/api/game/submit", json={"answer": ANSWERS[1]}, headers=good)
    teams = {t["team"]: t for t in client.get("/api/admin/teams", headers=admin).json()}
    client.patch(f"/api/admin/teams/{teams['Good']['team_id']}", json={"score_delta": -30}, headers=admin)
    client.patch(f"/api/admin/teams/{teams['=SUM(A1)']['team_id']}", json={"disqualified": True}, headers=admin)
    assert client.get("/api/game", headers=bad).status_code == 403
    board = client.get("/api/leaderboard").json()["rows"]
    assert [(r["team"], r["score"]) for r in board] == [("Good", 70)]

    export = client.get("/api/admin/export.csv", headers=admin)
    assert export.headers["content-type"].startswith("text/csv")
    lines = export.text.strip().splitlines()
    assert lines[0].startswith("rank,team,members,score")
    assert lines[1].startswith("1,Good,A; B,70,1,9,no")
    assert "'=SUM(A1)" in lines[2] and lines[2].endswith("yes")

    client.post(f"/api/admin/teams/{teams['Good']['team_id']}/reset", headers=admin)
    state = client.get("/api/game", headers=good).json()
    assert state["team"]["score"] == 0 and state["stages"][0]["status"] == "current"
    subs = client.get("/api/admin/submissions", headers=admin).json()
    assert subs == []


def test_admin_events_lifecycle(client):
    admin = admin_headers(client)
    second = client.post("/api/admin/events", json={"name": "Spring Hunt"}, headers=admin).json()
    assert second["is_active"] is False and second["status"] == "draft"
    first_id = client.get("/api/admin/events", headers=admin).json()[0]["id"]
    assert client.delete(f"/api/admin/events/{first_id}", headers=admin).status_code == 409
    client.post(f"/api/admin/events/{second['id']}/activate", headers=admin)
    assert client.get("/api/leaderboard").json()["event"]["name"] == "Spring Hunt"
    assert client.delete(f"/api/admin/events/{first_id}", headers=admin).status_code == 200
    assert client.get("/api/admin/overview", headers=admin).json()["puzzles"] == 0


def test_correct_answers_are_never_stored(client):
    team = register(client)
    client.post("/api/game/submit", json={"answer": "bad guess"}, headers=team)
    client.post("/api/game/submit", json={"answer": ANSWERS[1]}, headers=team)
    subs = client.get("/api/admin/submissions", headers=admin_headers(client)).json()
    assert json.dumps(subs).upper().count("COPPER") == 0
    assert [(s["answer"], s["correct"]) for s in subs] == [("", True), ("bad guess", False)]
