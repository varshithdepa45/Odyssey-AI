-- CodeHunt schema for Supabase (Postgres + pgvector).
-- The backend creates all of this by itself on first start; run this file by hand only if you
-- want the tables to exist before the first deploy. Generated from app/models.py.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS events (
	id SERIAL NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	registration_open BOOLEAN NOT NULL, 
	wrong_penalty INTEGER NOT NULL, 
	min_points INTEGER NOT NULL, 
	final_message TEXT NOT NULL, 
	team_size INTEGER NOT NULL, 
	questions_per_team INTEGER, 
	duration_minutes INTEGER, 
	default_points INTEGER NOT NULL, 
	hint_costs JSON NOT NULL, 
	completion_bonus INTEGER NOT NULL, 
	map_provider VARCHAR(16) NOT NULL, 
	map_image_url VARCHAR(500) NOT NULL, 
	map_lat FLOAT, 
	map_lng FLOAT, 
	map_zoom INTEGER NOT NULL, 
	started_at TIMESTAMP WITHOUT TIME ZONE, 
	ended_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);


CREATE TABLE IF NOT EXISTS schema_migrations (
	version SERIAL NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	applied_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (version)
);


CREATE TABLE IF NOT EXISTS documents (
	id SERIAL NOT NULL, 
	event_id INTEGER NOT NULL, 
	title VARCHAR(160) NOT NULL, 
	content TEXT NOT NULL, 
	kind VARCHAR(12) NOT NULL, 
	stage INTEGER NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(event_id) REFERENCES events (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_documents_event_id ON documents (event_id);

CREATE TABLE IF NOT EXISTS map_markers (
	id SERIAL NOT NULL, 
	event_id INTEGER NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	description TEXT NOT NULL, 
	directions TEXT NOT NULL, 
	kind VARCHAR(12) NOT NULL, 
	unlock VARCHAR(16) NOT NULL, 
	unlock_stage INTEGER, 
	x FLOAT NOT NULL, 
	y FLOAT NOT NULL, 
	lat FLOAT, 
	lng FLOAT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(event_id) REFERENCES events (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_map_markers_event_id ON map_markers (event_id);

CREATE TABLE IF NOT EXISTS puzzles (
	id SERIAL NOT NULL, 
	event_id INTEGER NOT NULL, 
	stage INTEGER NOT NULL, 
	title VARCHAR(120) NOT NULL, 
	cipher VARCHAR(24) NOT NULL, 
	prompt TEXT NOT NULL, 
	encoded_text TEXT NOT NULL, 
	points INTEGER NOT NULL, 
	answer_hashes JSON NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (event_id, stage), 
	FOREIGN KEY(event_id) REFERENCES events (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_puzzles_event_id ON puzzles (event_id);

CREATE TABLE IF NOT EXISTS teams (
	id SERIAL NOT NULL, 
	event_id INTEGER NOT NULL, 
	name VARCHAR(40) NOT NULL, 
	name_key VARCHAR(40) NOT NULL, 
	password_hash VARCHAR(200) NOT NULL, 
	members JSON NOT NULL, 
	score INTEGER NOT NULL, 
	disqualified BOOLEAN NOT NULL, 
	finished_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (event_id, name_key), 
	FOREIGN KEY(event_id) REFERENCES events (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_teams_event_id ON teams (event_id);

CREATE TABLE IF NOT EXISTS assignments (
	id SERIAL NOT NULL, 
	team_id INTEGER NOT NULL, 
	puzzle_id INTEGER NOT NULL, 
	position INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (team_id, puzzle_id), 
	UNIQUE (team_id, position), 
	FOREIGN KEY(team_id) REFERENCES teams (id) ON DELETE CASCADE, 
	FOREIGN KEY(puzzle_id) REFERENCES puzzles (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_assignments_team_id ON assignments (team_id);

CREATE TABLE IF NOT EXISTS chat_messages (
	id SERIAL NOT NULL, 
	team_id INTEGER NOT NULL, 
	kind VARCHAR(12) NOT NULL, 
	question TEXT NOT NULL, 
	answer TEXT NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(team_id) REFERENCES teams (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_chat_messages_team_id ON chat_messages (team_id);

CREATE TABLE IF NOT EXISTS doc_chunks (
	id SERIAL NOT NULL, 
	document_id INTEGER NOT NULL, 
	event_id INTEGER NOT NULL, 
	stage INTEGER NOT NULL, 
	title VARCHAR(160) NOT NULL, 
	content TEXT NOT NULL, 
	embedding vector(384) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_doc_chunks_event_id ON doc_chunks (event_id);
CREATE INDEX IF NOT EXISTS ix_doc_chunks_document_id ON doc_chunks (document_id);

CREATE TABLE IF NOT EXISTS hints (
	id SERIAL NOT NULL, 
	puzzle_id INTEGER NOT NULL, 
	position INTEGER NOT NULL, 
	text TEXT NOT NULL, 
	penalty INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(puzzle_id) REFERENCES puzzles (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_hints_puzzle_id ON hints (puzzle_id);

CREATE TABLE IF NOT EXISTS participants (
	id SERIAL NOT NULL, 
	event_id INTEGER NOT NULL, 
	team_id INTEGER, 
	name VARCHAR(60) NOT NULL, 
	identifier VARCHAR(80), 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (event_id, identifier), 
	FOREIGN KEY(event_id) REFERENCES events (id) ON DELETE CASCADE, 
	FOREIGN KEY(team_id) REFERENCES teams (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_participants_event_id ON participants (event_id);
CREATE INDEX IF NOT EXISTS ix_participants_team_id ON participants (team_id);

CREATE TABLE IF NOT EXISTS progress (
	id SERIAL NOT NULL, 
	team_id INTEGER NOT NULL, 
	puzzle_id INTEGER NOT NULL, 
	wrong_attempts INTEGER NOT NULL, 
	hints_used INTEGER NOT NULL, 
	penalty_total INTEGER NOT NULL, 
	points_awarded INTEGER NOT NULL, 
	solved_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (team_id, puzzle_id), 
	FOREIGN KEY(team_id) REFERENCES teams (id) ON DELETE CASCADE, 
	FOREIGN KEY(puzzle_id) REFERENCES puzzles (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_progress_team_id ON progress (team_id);

CREATE TABLE IF NOT EXISTS score_events (
	id SERIAL NOT NULL, 
	team_id INTEGER NOT NULL, 
	puzzle_id INTEGER, 
	kind VARCHAR(12) NOT NULL, 
	delta INTEGER NOT NULL, 
	note VARCHAR(200) NOT NULL, 
	dedupe_key VARCHAR(80), 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(team_id) REFERENCES teams (id) ON DELETE CASCADE, 
	FOREIGN KEY(puzzle_id) REFERENCES puzzles (id) ON DELETE SET NULL, 
	UNIQUE (dedupe_key)
);

CREATE INDEX IF NOT EXISTS ix_score_events_team_id ON score_events (team_id);

CREATE TABLE IF NOT EXISTS submissions (
	id SERIAL NOT NULL, 
	team_id INTEGER NOT NULL, 
	puzzle_id INTEGER NOT NULL, 
	answer VARCHAR(200) NOT NULL, 
	correct BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(team_id) REFERENCES teams (id) ON DELETE CASCADE, 
	FOREIGN KEY(puzzle_id) REFERENCES puzzles (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_submissions_team_id ON submissions (team_id);

CREATE INDEX IF NOT EXISTS doc_chunks_embedding_idx ON doc_chunks USING hnsw (embedding vector_cosine_ops);

-- Supabase serves every public table over its REST API. Row level security with no policies
-- blocks the anon and authenticated keys; the backend connects as the owner and is unaffected.
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE schema_migrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE map_markers ENABLE ROW LEVEL SECURITY;
ALTER TABLE puzzles ENABLE ROW LEVEL SECURITY;
ALTER TABLE teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE doc_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE hints ENABLE ROW LEVEL SECURITY;
ALTER TABLE participants ENABLE ROW LEVEL SECURITY;
ALTER TABLE progress ENABLE ROW LEVEL SECURITY;
ALTER TABLE score_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE submissions ENABLE ROW LEVEL SECURITY;
