-- ============================================================================
-- Job Search Platform — canonical PostgreSQL schema
-- Apply with:  psql -d jobsearch -f db/schema.sql
-- PostgreSQL 14+ (gen_random_uuid is built in since PG13)
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS citext;   -- case-insensitive emails

-- ---------------------------------------------------------------------------
-- Shared trigger: keep updated_at fresh on every UPDATE
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- Users & authentication
-- ---------------------------------------------------------------------------
CREATE TABLE users (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email               CITEXT      NOT NULL UNIQUE,
    password_hash       TEXT        NOT NULL,               -- bcrypt
    full_name           TEXT,
    -- Telegram linking: the web app shows a t.me deep link containing
    -- telegram_link_token; the bot's /start handler resolves it to this row
    -- and stores the chat id.
    telegram_chat_id    BIGINT      UNIQUE,
    telegram_link_token UUID        NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_users_updated BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- Search preferences (one user may run several saved searches)
-- ---------------------------------------------------------------------------
CREATE TABLE search_preferences (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id            BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name               TEXT        NOT NULL,                -- "Junior Backend TLV"
    title_keywords     TEXT[]      NOT NULL,                -- any-of, matched vs title + description
    must_have_keywords TEXT[]      NOT NULL DEFAULT '{}',   -- all-of, matched vs full text
    exclude_keywords   TEXT[]      NOT NULL DEFAULT '{}',   -- none-of
    locations          TEXT[]      NOT NULL DEFAULT '{}',   -- empty = anywhere
    remote_ok          BOOLEAN     NOT NULL DEFAULT TRUE,
    is_active          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_prefs_active ON search_preferences (user_id) WHERE is_active;
CREATE TRIGGER trg_prefs_updated BEFORE UPDATE ON search_preferences
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- Jobs fetched from external sources (shared across all users)
-- ---------------------------------------------------------------------------
CREATE TABLE jobs (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source        TEXT        NOT NULL,                     -- 'remotive', 'linkedin', ...
    external_id   TEXT        NOT NULL,                     -- id in the source system
    title         TEXT        NOT NULL,
    company       TEXT,
    location      TEXT,
    is_remote     BOOLEAN     NOT NULL DEFAULT FALSE,
    url           TEXT        NOT NULL,
    description   TEXT,
    posted_at     TIMESTAMPTZ,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Every new student job is broadcast once to the community Discord channel;
    -- NULL = not posted yet (gives retry semantics if the webhook call fails).
    discord_notified_at TIMESTAMPTZ,
    UNIQUE (source, external_id)                            -- dedup across poll cycles
);
CREATE INDEX idx_jobs_first_seen ON jobs (first_seen_at DESC);
CREATE INDEX idx_jobs_discord_unsent ON jobs (id) WHERE discord_notified_at IS NULL;

-- ---------------------------------------------------------------------------
-- Alerts: which job matched which user (and whether Telegram was notified).
-- UNIQUE(user_id, job_id) guarantees a user is never pinged twice for one job.
-- ---------------------------------------------------------------------------
CREATE TABLE job_alerts (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id       BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id        BIGINT      NOT NULL REFERENCES jobs(id)  ON DELETE CASCADE,
    preference_id BIGINT      REFERENCES search_preferences(id) ON DELETE SET NULL,
    matched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    notified_at   TIMESTAMPTZ,                              -- NULL = not yet sent
    dismissed     BOOLEAN     NOT NULL DEFAULT FALSE,
    UNIQUE (user_id, job_id)
);
CREATE INDEX idx_alerts_user ON job_alerts (user_id, matched_at DESC);
CREATE INDEX idx_alerts_unsent ON job_alerts (id) WHERE notified_at IS NULL;

-- ---------------------------------------------------------------------------
-- Kanban application tracker (CRM)
-- ---------------------------------------------------------------------------
CREATE TYPE application_status AS ENUM (
    'applied', 'phone_interview', 'home_assignment',
    'technical_interview', 'rejected', 'offer'
);

CREATE TABLE applications (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id    BIGINT             NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id     BIGINT             REFERENCES jobs(id) ON DELETE SET NULL,  -- NULL = manual entry
    company    TEXT               NOT NULL,
    title      TEXT               NOT NULL,
    url        TEXT,
    status     application_status NOT NULL DEFAULT 'applied',
    -- Fractional ordering for drag & drop: to move a card between two cards,
    -- set sort_order to the midpoint of their values. No mass renumbering.
    sort_order DOUBLE PRECISION   NOT NULL DEFAULT 0,
    notes      TEXT,
    applied_at DATE               NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ        NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ        NOT NULL DEFAULT now()
);
CREATE INDEX idx_apps_board ON applications (user_id, status, sort_order);
CREATE TRIGGER trg_apps_updated BEFORE UPDATE ON applications
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Status-change history (drives "3 weeks in Phone Interview" insights)
CREATE TABLE application_events (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id BIGINT             NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    from_status    application_status,                      -- NULL on creation
    to_status      application_status NOT NULL,
    changed_at     TIMESTAMPTZ        NOT NULL DEFAULT now()
);
CREATE INDEX idx_events_app ON application_events (application_id, changed_at);

-- ---------------------------------------------------------------------------
-- Resumes (PDF upload + simulated-ATS extraction result)
-- ---------------------------------------------------------------------------
CREATE TABLE resumes (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id           BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    original_filename TEXT        NOT NULL,
    storage_path      TEXT        NOT NULL,                 -- path on the VM disk
    raw_text          TEXT,                                 -- filled by worker
    extracted         JSONB,                                -- {skills:[], emails:[], sections:{}, ...}
    parse_status      TEXT        NOT NULL DEFAULT 'pending'
                      CHECK (parse_status IN ('pending', 'done', 'failed')),
    is_primary        BOOLEAN     NOT NULL DEFAULT FALSE,
    uploaded_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_resumes_user ON resumes (user_id, uploaded_at DESC);
-- At most one primary resume per user
CREATE UNIQUE INDEX one_primary_resume ON resumes (user_id) WHERE is_primary;

-- ---------------------------------------------------------------------------
-- AI generations: resume tailoring runs, cover letters, LinkedIn messages.
-- Rows are created 'pending' by the API and completed by the worker,
-- so the frontend can poll GET /ai/generations/{id}.
-- ---------------------------------------------------------------------------
CREATE TYPE generation_kind AS ENUM ('resume_tailoring', 'cover_letter', 'linkedin_message');

CREATE TABLE ai_generations (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         BIGINT          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    resume_id       BIGINT          REFERENCES resumes(id)      ON DELETE SET NULL,
    application_id  BIGINT          REFERENCES applications(id) ON DELETE SET NULL,
    kind            generation_kind NOT NULL,
    job_description TEXT            NOT NULL,
    result          JSONB,          -- tailoring: {missing_keywords, rewrites:[{original,rewritten,keywords}], ats_score_before, ats_score_after}
                                    -- cover_letter / linkedin_message: {text}
    status          TEXT            NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'done', 'failed')),
    error           TEXT,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ
);
CREATE INDEX idx_generations_user ON ai_generations (user_id, created_at DESC);
