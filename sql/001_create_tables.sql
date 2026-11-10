-- =====================================================================
-- 001_create_tables.sql
-- Creates the 4 warehouse tables described in DATA_DICTIONARY.md.
-- HOW TO RUN: Supabase -> SQL Editor (left menu, ">_" icon) -> paste all -> Run.
-- Safe to run more than once ("IF NOT EXISTS" skips tables that exist).
-- =====================================================================


-- 1) INVESTORS: one row per firm. This is the main output.
CREATE TABLE IF NOT EXISTS investors (
    investor_id          BIGSERIAL PRIMARY KEY,      -- auto-numbered ID (1, 2, 3...)
    firm_name            TEXT NOT NULL,              -- NOT NULL = must always have a value
    firm_type            TEXT,
    website              TEXT,
    country              TEXT,
    city                 TEXT,
    address              TEXT,
    aum_usd              NUMERIC,                    -- NUMERIC = a number (can be very large)
    sectors              TEXT,
    stages               TEXT,
    invests_in_funds     TEXT DEFAULT 'unknown',     -- yes / no / unknown
    ticket_size_min_usd  NUMERIC,
    ticket_size_max_usd  NUMERIC,
    firm_linkedin        TEXT,
    firm_email           TEXT,
    firm_phone           TEXT,
    legal_id             TEXT,
    is_blacklisted       BOOLEAN DEFAULT FALSE,      -- BOOLEAN = true/false
    in_company_hub       BOOLEAN DEFAULT FALSE,
    source_names         TEXT,
    source_urls          TEXT,
    last_updated         TIMESTAMPTZ DEFAULT NOW()   -- date + time, filled in automatically
);

-- A firm's website is the best way to spot duplicates, so the same
-- website can't appear twice (empty websites are allowed many times).
CREATE UNIQUE INDEX IF NOT EXISTS investors_website_unique
    ON investors (LOWER(website)) WHERE website IS NOT NULL;


-- 2) CONTACTS: people at each firm (one firm can have many contacts).
CREATE TABLE IF NOT EXISTS contacts (
    contact_id    BIGSERIAL PRIMARY KEY,
    investor_id   BIGINT REFERENCES investors(investor_id) ON DELETE CASCADE,
                  -- REFERENCES = links each contact to a firm.
                  -- ON DELETE CASCADE = deleting a firm deletes its contacts too.
    full_name     TEXT NOT NULL,
    title         TEXT,
    email         TEXT,
    phone         TEXT,
    linkedin      TEXT,
    source_name   TEXT,
    last_updated  TIMESTAMPTZ DEFAULT NOW()
);


-- 3) BLACKLIST: firms we must never include.
CREATE TABLE IF NOT EXISTS blacklist (
    blacklist_id  BIGSERIAL PRIMARY KEY,
    firm_name     TEXT NOT NULL,
    website       TEXT,
    reason        TEXT,
    source_name   TEXT
);


-- 4) SOURCES: tracks progress on each of our ~507 sources.
CREATE TABLE IF NOT EXISTS sources (
    source_id          BIGSERIAL PRIMARY KEY,
    source_name        TEXT NOT NULL,
    url                TEXT,
    method             TEXT,     -- api / bulk download / scrape / free-tier login / manual
    status             TEXT DEFAULT 'not started',
    records_extracted  INTEGER DEFAULT 0,
    notes              TEXT
);


-- Quick check: this should list the 4 tables.
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' ORDER BY table_name;
