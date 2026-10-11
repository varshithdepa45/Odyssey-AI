# CodeHunt

An AI-powered campus treasure hunt: cipher questions, a retrieval-augmented "Oracle" chatbot built into
the player dashboard, an interactive campus map that reveals places as teams progress, a live
leaderboard, and an organiser control room.

- **Frontend:** React, Vite, Tailwind CSS (`frontend/`)
- **Backend:** FastAPI, SQLAlchemy (`backend/`)
- **Database:** Supabase Postgres with pgvector in production, SQLite for local development
- **AI:** optional and swappable. The default costs nothing.

## Run it locally

You need Python 3.11+ and Node 20+.

```bash
# Terminal 1: backend on http://localhost:8010
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env          # skip if .env already exists; then fill in the secrets
.venv/bin/uvicorn app.main:app --reload --port 8010

# Terminal 2: frontend on http://localhost:5173
cd frontend
npm install
cp .env.example .env
npm run dev
```

On first start the backend creates its tables and seeds nine placeholder questions (three hints each), a
17-document archive and a placeholder map. On later starts it applies any pending database migrations
by itself. Then:

1. Open `http://localhost:5173/admin` and sign in with `ADMIN_USERNAME` / `ADMIN_PASSWORD` from `backend/.env`.
2. On the **Event** tab press **Go live**. Teams cannot see or submit anything while the event is a draft.
3. Register a team at `http://localhost:5173/register` and play.

Placeholder answers for testing are in `backend/app/seed.py` (`PUZZLES`). The admin page is not linked
from the public navigation; reach it by URL.

### Tests

```bash
cd backend && .venv/bin/python -m pytest -q
```

53 tests. Beyond the basics (ciphers, auth, unlocking, retrieval, admin operations, rate limits) they
cover simultaneous submissions, repeated hint requests, every score deduction, ranking after each score
change, attempts to reach hidden map markers, prompt injection, the reply guard, participant import,
team formation, question assignment, the event clock, and upgrading an old database. They run on SQLite
by default; set `TEST_DATABASE_URL` to a Postgres URL to run them against pgvector.

If you already had a database from the first version, it is upgraded in place on the next start. To get
the new placeholder content (third hints, completion bonus) on a local database you do not care about:
`cd backend && .venv/bin/python -m app.seed --reset`. That deletes every event, team and score.

## How the game works

- **Questions** unlock in order. Each team plays either the event's questions in number order (the
  default, optionally limited to the first N) or its own assigned list.
- **Answers** are checked on the server, ignoring case, spaces and punctuation (`Copper-Falcon!` equals
  `COPPER FALCON`).
- **Scoring** is a ledger: every gain or loss is one row, and a team's score is the sum of its rows.
  A correct answer adds the question's points. A wrong answer and each hint deduct their cost at once.
  Deductions on one question stop when it would be worth less than the floor. Finishing every assigned
  question adds the completion bonus. Defaults: +100 correct, −5 wrong, hints −10/−20/−30, +100 bonus,
  floor 20.
- **Leaderboard:** overall and per question, refreshed every 5 seconds. Overall ties break by more
  questions solved, then earlier finish, then earlier last solve, then fewer hints.
- **Finale:** the final message and any "after finish" map markers go only to teams that solved everything.

### Organiser controls (`/admin`)

| Tab | What you do there |
| --- | --- |
| Event | Start, pause, end; duration; team size (1 = individual); questions per team; all scoring values; final message |
| People | Add or import participants, form teams automatically, create teams, move people, export the list |
| Teams | Scores, adjustments with a reason, disqualify, reset, passwords; question assignments, manual or automatic |
| Puzzles | Questions, write-only answers, hints and their costs, the clue encoder |
| Archive | The Oracle's documents, genuine and decoy, and the stage each unlocks at |
| Map | Map source, markers, and when each marker becomes visible |
| History | Score ledger, hint log, attempts, and four CSV exports |

**Participants and teams.** Nothing assumes a head count. Paste a list on the People tab (one per line:
`name, identifier, team`; only the name is required), then press *Form teams automatically* to group
everyone without a team by the event's team size. With a team size of 1 each person gets their own
entry. Teams you create this way get a generated password, shown once with a CSV download. Teams can
also still register themselves while registration is open. Late arrivals: add them and form teams again;
only people without a team are touched.

**Question assignment.** On the Teams tab, *Assign automatically* gives each team N questions, either
rotating the starting question so teams spread out or picking at random. Or type a team's list by hand
(`5, 2, 8`). A list is rejected if it repeats a question, names one that does not exist, or drops one
the team has already started. Teams that are already playing are skipped by the automatic assignment.

### The Oracle chatbot

It sits beside the current question on the dashboard and does three things:

- **Explains** cipher techniques from the archive (retrieval over pgvector), the rules and scoring from
  the event's live settings, and the team's next permitted step.
- **Releases hints** one at a time. The hint button, or asking for a hint in words, shows the hint
  number and price and waits for a yes. The charge and the reveal happen in one database transaction,
  keyed to the hint number, so a failed request costs nothing and a repeated one never charges twice.
- **Refuses** to give answers, locations or its instructions.

How the refusal is enforced, in order: the model is never given an answer or a locked marker; messages
that try to override instructions or ask for answers are turned away before any model is called; archive
excerpts that contain a protected answer or a locked place name are dropped; and every model reply is
scanned for protected answers (by hashing each phrase and comparing with the stored answer hashes) and
for locked place names before it is sent. Phrases the player typed themselves are ignored by that scan,
so the chatbot cannot be used to test guesses for free.

### The map

Three sources, chosen on the Map tab:

| Source | Needs | Marker positions |
| --- | --- | --- |
| Placeholder schematic (default) | Nothing | X/Y percentages |
| Campus map image | A public image URL | X/Y percentages; click the preview to place |
| OpenStreetMap | Centre latitude/longitude | Latitude/longitude per marker |

Each marker has a visibility rule: always, when a team reaches question N, when it solves question N,
or when it finishes. The server filters markers per team before responding, so a locked marker's name
and coordinates are never in the page, the bundle or any network response. The seeded map has two
public landmarks, one hidden checkpoint per question, and a hidden final destination, all with made-up
positions and placeholder names for you to replace.

## Keeping the secrets secret

| Secret | Where it lives | Who can read it |
| --- | --- | --- |
| Puzzle answers | `puzzles.answer_hashes`, as HMAC-SHA256 digests keyed by `ANSWER_PEPPER` | Nobody. Not the API, not the admin page, not someone with a database dump |
| Final message | `events.final_message` | Admins, and teams that have finished |
| Map markers | `map_markers`, filtered per team on the server | Admins, and teams that have met the marker's unlock rule |
| Locked stages | Never sent to a team that has not reached them | |
| API keys | Backend environment variables only | |
| Real answers for seeding | `backend/private/game_secrets.json`, git-ignored | Whoever has your laptop |

The frontend bundle contains no game content at all. The chatbot is only ever shown archive documents, so
it has no answers to leak. **Rule for organisers: never type a location, an answer, or the final
destination into an archive document.** Everything in the archive is searchable by players.

`game_secrets.json` holds the answers only. It deliberately does not record which paper forms which
letter, or name the final destination; that knowledge stays with the organisers and the physical papers.
The final message it ships with tells teams how to lay their papers out without naming the place. Edit it
if you would rather spell it out. Seeding with `--private` names each checkpoint marker after its answer
(still hidden until that question is solved). The final destination marker stays a placeholder: name
and position it yourself on the Map tab, where it remains hidden until a team finishes.

### Loading the real clues

Either way, the clue text is generated from the answer, so the stages are solvable as soon as they are loaded.

- **From the admin page:** Puzzles tab, open a stage, type the new answer (several accepted spellings
  separated by `|`), use the **Clue encoder** at the bottom to produce the cipher text, paste it into
  *Encoded clue text*, save.
- **From the file:** edit `backend/private/game_secrets.json`, then
  `cd backend && .venv/bin/python -m app.seed --reset --private`. `--reset` deletes every event, team and
  score first. To load a hosted database this way, run it from your laptop with `DATABASE_URL` and
  `ANSWER_PEPPER` set to the production values; the pepper must match or no answer will ever be accepted.

The Caesar shift, Vigenère keyword and book-cipher passage are constants at the top of `seed.py`, and the
archive documents quote them. If you change one in the admin page, update the matching archive document.

## AI providers and what they cost

A Claude Pro subscription covers the Claude apps. It does not include API credit: the Anthropic API is
billed separately, pay as you go, through the Anthropic Console. So the app does not assume you have any.

Set `AI_PROVIDER` in `backend/.env`:

| Setting | Cost | Notes |
| --- | --- | --- |
| `none` (default) | Free | The Oracle returns the retrieved records verbatim, with no AI-written summary. Retrieval, stage gating and decoys all still work. |
| `openai_compatible` + Gemini or Groq | Free tier | Both offer free API keys with rate limits. Limits change, so check the provider's page before the event. |
| `openai_compatible` + Ollama | Free | Runs a model on your own machine; only useful if the backend runs there too. |
| `anthropic` | Paid | Uses the official SDK. |

Rough Anthropic cost, assuming about 1,000 input tokens (instructions plus four excerpts) and 300 output
tokens per question, at list prices as of October 2026:

| Model | Price per million tokens (in / out) | Per question | 30 teams using all 80 daily questions |
| --- | --- | --- | --- |
| `claude-haiku-5-5` | $0.10 / $0.50 | about $0.00025 | about $0.60 |
| `claude-opus-5-5` | $4 / $20 | about $0.01 | about $24 |

These are estimates; check current pricing before you commit. For a few-sentence answer over four short
excerpts the cheaper model is plenty. `CHAT_DAILY_LIMIT` and `CHAT_PER_MINUTE` put a hard ceiling on
spend, and if the provider errors or runs out of credit the Oracle falls back to returning the records.

**Embeddings** default to `hash`: a built-in feature-hashing embedder that needs no model, no network and
no money. It matches on shared wording rather than meaning, which works for a small archive where players
name the cipher they are asking about. For semantic matching set `EMBEDDING_PROVIDER=openai_compatible`
with an `/embeddings` endpoint, set `EMBEDDING_DIM` to match, and press **Re-index all** on the Archive tab.
The vector column's size is fixed when the table is created, so decide before the first production deploy.

## Deploy for free

The free tiers below are enough for a campus event. All three change their terms from time to time.

### 1. Database: Supabase

1. Create a project at supabase.com and choose a database password.
2. Open **Connect**, pick **Session pooler**, and copy the URI. It looks like
   `postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres`.
   Use the pooler rather than the direct connection, which is IPv6-only on the free plan.
3. That is all. On first start the backend enables pgvector, creates the tables, and turns on row level
   security for every table so Supabase's public REST API cannot read them. `backend/schema.sql` has the
   same statements if you would rather run them yourself in the SQL editor.

### 2. Backend: Render

1. Push this repository to GitHub (`git init && git add . && git commit -m "CodeHunt"`, then create a repo and push). Check that `git status` never lists `.env` or `backend/private/game_secrets.json`.
2. On render.com choose **New > Blueprint** and select the repo; `render.yaml` supplies the settings. Or
   create a **Web Service** by hand: root directory `backend`, build `pip install -r requirements.txt`,
   start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, free instance.
3. Set the environment variables: `DATABASE_URL` (from Supabase), `ADMIN_PASSWORD`, `CORS_ORIGINS` (your
   frontend URL, added after step 3 below), and any `AI_*` values. The blueprint generates `SECRET_KEY`
   and `ANSWER_PEPPER`. With `ENV=production` the server refuses to start while a secret is still a default.
4. Check `https://<your-service>.onrender.com/api/health` returns `{"ok":true}`.

### 3. Frontend: Vercel

1. On vercel.com import the repo, set the root directory to `frontend`. Vercel detects Vite.
2. Add the environment variable `VITE_API_URL=https://<your-service>.onrender.com`.
3. Deploy, then put the resulting URL into `CORS_ORIGINS` on Render (no trailing slash).

Netlify and Cloudflare Pages work the same way: build `npm run build`, publish `dist`. The repo includes
the single-page-app rewrites for Vercel (`vercel.json`) and Netlify/Cloudflare (`public/_redirects`).

### Event-day checklist

- Free Render instances sleep after a quiet spell and take up to a minute to wake. Open the site a few
  minutes before the start, and keep the leaderboard open on one screen so it stays awake.
- Free Supabase projects pause after about a week without activity. Unpause it the day before.
- Set the map source and give every marker its real name, position and directions (Map tab).
- Load the real clues, then register a throwaway team and solve stage 1 to confirm the answer hashes
  match. Delete that team from the Teams tab afterwards.
- Leave the event in **draft** until the start signal. Completion time is measured from the first **Go live**.
- Afterwards: Teams tab, **Export CSV**.

## Database migrations

Schema changes live in `backend/app/migrations.py` as numbered steps. The backend applies pending steps
on every start and records them in `schema_migrations`, so deploying new code is the migration; there
is no separate command to remember on hosts without a shell. To run them by hand:
`cd backend && .venv/bin/python -m app.migrate`. `backend/schema.sql` is the current full schema for
reference.

## Limits worth knowing

- The hint texts are written by organisers and delivered by the chatbot; the model does not invent hints. That is deliberate: a model writing hints for a puzzle would need the answer.
- The reply scan matches whole phrases of up to six words. It will not catch an answer a model spells out one letter at a time or translates. With `AI_PROVIDER=none` no model writes anything, so this does not arise.
- The event clock measures from the first Go live and does not stop while the event is paused.
- The OpenStreetMap source loads tiles from openstreetmap.org, which is fine for one campus event; for heavy use set `VITE_MAP_TILE_URL` to a provider of your own.

- Rate limits are held in memory, so they assume one backend instance (what the free tier gives you) and reset on restart. The daily Oracle cap is stored in the database and survives restarts.
- There is one admin account, set by environment variables.
- Login tokens live in the browser's local storage and last `TOKEN_HOURS` (12 by default).
- The leaderboard polls every 5 seconds rather than using websockets. Scores themselves change the instant a request is processed.
- The Anthropic and OpenAI-compatible calls are exercised in tests with a stubbed model, not against live APIs. Ask the Oracle one question after configuring a provider; replies written by a model show an AI-written summary instead of the bracketed raw records.
