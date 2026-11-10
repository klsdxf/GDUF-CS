BEGIN TRANSACTION;
CREATE TABLE active_member_claims (
	competition_id VARCHAR NOT NULL, 
	steam_id VARCHAR(17) NOT NULL, 
	registration_id VARCHAR NOT NULL, 
	PRIMARY KEY (competition_id, steam_id), 
	FOREIGN KEY(competition_id) REFERENCES competitions (id), 
	FOREIGN KEY(registration_id) REFERENCES registrations (id)
);
CREATE TABLE admin_sessions (
	token_hash VARCHAR(64) NOT NULL, 
	csrf VARCHAR NOT NULL, 
	expires_at DATETIME NOT NULL, 
	PRIMARY KEY (token_hash)
);
CREATE TABLE admins (
	id INTEGER NOT NULL, 
	username VARCHAR(80) NOT NULL, 
	password_hash VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (id = 1), 
	UNIQUE (username)
);
CREATE TABLE announcements (
	id VARCHAR NOT NULL, 
	competition_id VARCHAR NOT NULL, 
	title VARCHAR NOT NULL, 
	body VARCHAR NOT NULL, 
	published BOOLEAN NOT NULL, 
	pinned BOOLEAN NOT NULL, 
	publish_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(competition_id) REFERENCES competitions (id)
);
CREATE TABLE audit_logs (
	id VARCHAR NOT NULL, 
	action VARCHAR NOT NULL, 
	entity_id VARCHAR NOT NULL, 
	payload JSON NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE competition_partners (
	id VARCHAR NOT NULL, 
	competition_id VARCHAR NOT NULL, 
	sponsor_id VARCHAR NOT NULL, 
	tier VARCHAR NOT NULL, 
	data JSON NOT NULL, 
	published BOOLEAN NOT NULL, 
	version INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (competition_id, sponsor_id), 
	FOREIGN KEY(competition_id) REFERENCES competitions (id), 
	FOREIGN KEY(sponsor_id) REFERENCES sponsors (id), 
	UNIQUE (id, competition_id)
);
CREATE TABLE competition_result_pages (
	id VARCHAR NOT NULL, 
	competition_id VARCHAR NOT NULL, 
	version INTEGER NOT NULL, 
	config JSON NOT NULL, 
	current_release_id VARCHAR, 
	PRIMARY KEY (id), 
	UNIQUE (competition_id), 
	FOREIGN KEY(competition_id) REFERENCES competitions (id), 
	CONSTRAINT fk_current_release FOREIGN KEY(current_release_id) REFERENCES result_releases (id), 
	UNIQUE (id, competition_id), 
	CONSTRAINT fk_release_belongs_to_page FOREIGN KEY(current_release_id, id) REFERENCES result_releases (id, result_page_id)
);
CREATE TABLE competitions (
	id VARCHAR NOT NULL, 
	slug VARCHAR(100) NOT NULL, 
	name VARCHAR NOT NULL, 
	season VARCHAR NOT NULL, 
	organizer VARCHAR NOT NULL, 
	description VARCHAR NOT NULL, 
	rules VARCHAR NOT NULL, 
	map_pool JSON NOT NULL, 
	config JSON NOT NULL, 
	status VARCHAR NOT NULL, 
	published BOOLEAN NOT NULL, 
	is_default BOOLEAN NOT NULL, 
	team_limit INTEGER NOT NULL, 
	revision INTEGER NOT NULL, 
	focus_match_id VARCHAR, 
	PRIMARY KEY (id), 
	UNIQUE (slug)
);
CREATE TABLE import_batches (
	id VARCHAR NOT NULL, 
	competition_id VARCHAR NOT NULL, 
	revision INTEGER NOT NULL, 
	mode VARCHAR NOT NULL, 
	filename VARCHAR NOT NULL, 
	file_hash VARCHAR NOT NULL, 
	payload JSON NOT NULL, 
	expires_at DATETIME NOT NULL, 
	status VARCHAR NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(competition_id) REFERENCES competitions (id)
);
CREATE TABLE live_streams (
	id VARCHAR NOT NULL, 
	competition_id VARCHAR NOT NULL, 
	match_id VARCHAR, 
	room_url VARCHAR NOT NULL, 
	replay_url VARCHAR NOT NULL, 
	status VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(competition_id) REFERENCES competitions (id), 
	FOREIGN KEY(match_id) REFERENCES matches (id)
);
CREATE TABLE match_advancements (
	id VARCHAR NOT NULL, 
	source VARCHAR NOT NULL, 
	outcome VARCHAR NOT NULL, 
	target VARCHAR NOT NULL, 
	slot VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (target, slot), 
	FOREIGN KEY(source) REFERENCES matches (id), 
	FOREIGN KEY(target) REFERENCES matches (id)
);
CREATE TABLE matches (
	id VARCHAR NOT NULL, 
	competition_id VARCHAR NOT NULL, 
	stage_id VARCHAR NOT NULL, 
	code VARCHAR NOT NULL, 
	round INTEGER NOT NULL, 
	"group" VARCHAR NOT NULL, 
	bracket VARCHAR NOT NULL, 
	a VARCHAR, 
	b VARCHAR, 
	source_a VARCHAR NOT NULL, 
	source_b VARCHAR NOT NULL, 
	best_of INTEGER NOT NULL, 
	scheduled_at DATETIME, 
	status VARCHAR NOT NULL, 
	published BOOLEAN NOT NULL, 
	result JSON NOT NULL, 
	draft_result JSON NOT NULL, 
	winner VARCHAR, 
	confirmed BOOLEAN NOT NULL, 
	version INTEGER NOT NULL, 
	rosters JSON NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (stage_id, code), 
	CHECK (best_of IN (1,3,5)), 
	CHECK (a IS NULL OR b IS NULL OR a <> b), 
	FOREIGN KEY(competition_id) REFERENCES competitions (id), 
	FOREIGN KEY(stage_id) REFERENCES stages (id), 
	FOREIGN KEY(a) REFERENCES registrations (id), 
	FOREIGN KEY(b) REFERENCES registrations (id), 
	FOREIGN KEY(winner) REFERENCES registrations (id), 
	UNIQUE (id, competition_id)
);
CREATE TABLE prize_allocations (
	competition_id VARCHAR NOT NULL, 
	id VARCHAR NOT NULL, 
	placement_id VARCHAR NOT NULL, 
	prize_id VARCHAR NOT NULL, 
	quantity INTEGER NOT NULL, 
	data JSON NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (placement_id, prize_id), 
	CHECK (quantity > 0), 
	FOREIGN KEY(competition_id) REFERENCES competitions (id), 
	FOREIGN KEY(placement_id) REFERENCES result_placements (id), 
	FOREIGN KEY(prize_id) REFERENCES prizes (id), 
	FOREIGN KEY(placement_id, competition_id) REFERENCES result_placements (id, competition_id), 
	FOREIGN KEY(prize_id, competition_id) REFERENCES prizes (id, competition_id)
);
CREATE TABLE prizes (
	id VARCHAR NOT NULL, 
	competition_id VARCHAR NOT NULL, 
	provider_partner_id VARCHAR NOT NULL, 
	name VARCHAR NOT NULL, 
	data JSON NOT NULL, 
	active BOOLEAN NOT NULL, 
	version INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(competition_id) REFERENCES competitions (id), 
	FOREIGN KEY(provider_partner_id) REFERENCES competition_partners (id), 
	UNIQUE (id, competition_id), 
	FOREIGN KEY(provider_partner_id, competition_id) REFERENCES competition_partners (id, competition_id)
);
CREATE TABLE registration_members (
	id VARCHAR NOT NULL, 
	registration_id VARCHAR NOT NULL, 
	version INTEGER NOT NULL, 
	steam_id VARCHAR(17) NOT NULL, 
	nickname VARCHAR(100) NOT NULL, 
	role VARCHAR NOT NULL, 
	captain BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (registration_id, version, steam_id), 
	FOREIGN KEY(registration_id) REFERENCES registrations (id)
);
CREATE TABLE registrations (
	id VARCHAR NOT NULL, 
	competition_id VARCHAR NOT NULL, 
	code VARCHAR(32) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description VARCHAR NOT NULL, 
	contact VARCHAR(200) NOT NULL, 
	logo VARCHAR NOT NULL, 
	english_name VARCHAR(120) NOT NULL, 
	emblem_text VARCHAR(12) NOT NULL, 
	poster_title_lines JSON NOT NULL, 
	active BOOLEAN NOT NULL, 
	version INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (competition_id, code), 
	FOREIGN KEY(competition_id) REFERENCES competitions (id), 
	UNIQUE (id, competition_id)
);
CREATE TABLE result_path_matches (
	competition_id VARCHAR NOT NULL, 
	id VARCHAR NOT NULL, 
	result_page_id VARCHAR NOT NULL, 
	match_id VARCHAR NOT NULL, 
	display_order INTEGER NOT NULL, 
	stage_label VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (result_page_id, match_id), 
	UNIQUE (result_page_id, display_order), 
	FOREIGN KEY(competition_id) REFERENCES competitions (id), 
	FOREIGN KEY(result_page_id) REFERENCES competition_result_pages (id), 
	FOREIGN KEY(match_id) REFERENCES matches (id), 
	FOREIGN KEY(result_page_id, competition_id) REFERENCES competition_result_pages (id, competition_id), 
	FOREIGN KEY(match_id, competition_id) REFERENCES matches (id, competition_id)
);
CREATE TABLE result_placements (
	competition_id VARCHAR NOT NULL, 
	id VARCHAR NOT NULL, 
	result_page_id VARCHAR NOT NULL, 
	registration_id VARCHAR NOT NULL, 
	team_display_version INTEGER NOT NULL, 
	rank_from INTEGER NOT NULL, 
	rank_to INTEGER NOT NULL, 
	data JSON NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (result_page_id, registration_id), 
	CHECK (rank_from >= 1 AND rank_to >= rank_from AND rank_to <= 32), 
	FOREIGN KEY(competition_id) REFERENCES competitions (id), 
	FOREIGN KEY(result_page_id) REFERENCES competition_result_pages (id), 
	FOREIGN KEY(registration_id) REFERENCES registrations (id), 
	UNIQUE (id, competition_id), 
	FOREIGN KEY(result_page_id, competition_id) REFERENCES competition_result_pages (id, competition_id), 
	FOREIGN KEY(registration_id, competition_id) REFERENCES registrations (id, competition_id), 
	FOREIGN KEY(registration_id, team_display_version) REFERENCES roster_snapshots (registration_id, version)
);
CREATE TABLE result_releases (
	id VARCHAR NOT NULL, 
	result_page_id VARCHAR NOT NULL, 
	competition_id VARCHAR NOT NULL, 
	release_number INTEGER NOT NULL, 
	status VARCHAR NOT NULL, 
	source_fingerprint VARCHAR NOT NULL, 
	source_dependencies JSON NOT NULL, 
	public_snapshot JSON NOT NULL, 
	content_sha256 VARCHAR NOT NULL, 
	published_at DATETIME NOT NULL, 
	reason VARCHAR NOT NULL, 
	idempotency_key VARCHAR, 
	invalidated_at DATETIME, 
	invalidation_reason VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (result_page_id, release_number), 
	UNIQUE (result_page_id, idempotency_key), 
	FOREIGN KEY(result_page_id) REFERENCES competition_result_pages (id), 
	FOREIGN KEY(competition_id) REFERENCES competitions (id), 
	UNIQUE (id, competition_id), 
	FOREIGN KEY(result_page_id, competition_id) REFERENCES competition_result_pages (id, competition_id), 
	UNIQUE (id, result_page_id)
);
CREATE TABLE roster_snapshots (
	registration_id VARCHAR NOT NULL, 
	version INTEGER NOT NULL, 
	name VARCHAR NOT NULL, 
	description VARCHAR NOT NULL, 
	logo VARCHAR NOT NULL, 
	english_name VARCHAR(120) NOT NULL, 
	emblem_text VARCHAR(12) NOT NULL, 
	poster_title_lines JSON NOT NULL, 
	PRIMARY KEY (registration_id, version), 
	FOREIGN KEY(registration_id) REFERENCES registrations (id)
);
CREATE TABLE sponsors (
	id VARCHAR NOT NULL, 
	name VARCHAR NOT NULL, 
	data JSON NOT NULL, 
	active BOOLEAN NOT NULL, 
	version INTEGER NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE stages (
	id VARCHAR NOT NULL, 
	competition_id VARCHAR NOT NULL, 
	name VARCHAR NOT NULL, 
	type VARCHAR NOT NULL, 
	config JSON NOT NULL, 
	entries JSON NOT NULL, 
	status VARCHAR NOT NULL, 
	generation_key VARCHAR, 
	PRIMARY KEY (id), 
	FOREIGN KEY(competition_id) REFERENCES competitions (id), 
	UNIQUE (id, competition_id)
);
CREATE INDEX ix_registrations_competition_id ON registrations (competition_id);
CREATE INDEX ix_import_batches_competition_id ON import_batches (competition_id);
CREATE INDEX ix_stages_competition_id ON stages (competition_id);
CREATE INDEX ix_announcements_competition_id ON announcements (competition_id);
CREATE UNIQUE INDEX uq_presenting_partner ON competition_partners (competition_id) WHERE tier = 'presenting';
CREATE INDEX ix_registration_members_registration_id ON registration_members (registration_id);
CREATE INDEX ix_matches_stage_id ON matches (stage_id);
CREATE INDEX ix_matches_scheduled_at ON matches (scheduled_at);
CREATE INDEX ix_matches_competition_id ON matches (competition_id);
CREATE INDEX ix_live_streams_competition_id ON live_streams (competition_id);
COMMIT;
CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY);
INSERT INTO alembic_version VALUES ('003');

