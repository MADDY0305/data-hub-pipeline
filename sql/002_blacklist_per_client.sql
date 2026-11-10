-- =====================================================================
-- 002_blacklist_per_client.sql
-- Our 32 blacklists are named after client funds (e.g. "Client A").
-- So a blacklist entry means "don't use this investor FOR THAT CLIENT",
-- not "delete this investor". This adds a "client" column to record that.
-- HOW TO RUN: Supabase -> SQL Editor -> paste -> Run. Safe to run twice.
-- =====================================================================

-- ALTER TABLE = change an existing table. Here: add one new column.
ALTER TABLE blacklist ADD COLUMN IF NOT EXISTS client TEXT;

-- Link a blacklist row to an investor once we've matched them.
ALTER TABLE blacklist ADD COLUMN IF NOT EXISTS investor_id BIGINT
    REFERENCES investors(investor_id) ON DELETE SET NULL;

-- "is_blacklisted" on investors now means: on AT LEAST ONE client's list.
-- To see which clients, you'll query the blacklist table, e.g.:
--   SELECT client FROM blacklist WHERE investor_id = 1042;

-- Check: shows the blacklist table's columns.
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'blacklist' ORDER BY ordinal_position;
