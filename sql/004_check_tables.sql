-- =====================================================================
-- 004_check_tables.sql - quick health check of the whole warehouse.
-- HOW TO RUN: Supabase -> SQL Editor -> paste ONE block -> Run.
-- (The editor shows only the LAST result, so run the blocks one by one.)
-- =====================================================================


-- 1) Row counts of all 4 tables in ONE result.
--    UNION ALL = stack several results on top of each other.
SELECT 'investors' AS table_name, COUNT(*) AS row_count FROM investors
UNION ALL SELECT 'contacts',  COUNT(*) FROM contacts
UNION ALL SELECT 'blacklist', COUNT(*) FROM blacklist
UNION ALL SELECT 'sources',   COUNT(*) FROM sources;


-- 2) First 5 rows of each table ("head").   LIMIT = only return N rows.
SELECT * FROM investors ORDER BY investor_id  LIMIT 5;

SELECT * FROM contacts  ORDER BY contact_id   LIMIT 5;

SELECT * FROM blacklist ORDER BY blacklist_id LIMIT 5;

SELECT * FROM sources   ORDER BY source_id    LIMIT 5;


-- 3) Is the SEC data in?  (SEC funds carry an "SEC CIK" id in legal_id)
SELECT COUNT(*)                                   AS sec_investors,
       COUNT(*) FILTER (WHERE firm_type = 'Venture Capital') AS venture_capital,
       COUNT(*) FILTER (WHERE firm_type = 'Private Equity')  AS private_equity
FROM investors
WHERE legal_id LIKE 'SEC CIK%';

SELECT COUNT(*) AS sec_people
FROM contacts
WHERE source_name LIKE '%SEC EDGAR%';

--    A peek at 5 SEC funds with their phone and address:
SELECT firm_name, firm_type, city, firm_phone, address, legal_id
FROM investors
WHERE legal_id LIKE 'SEC CIK%'
LIMIT 5;


-- 4) Sanity checks for the bugs we fixed (each should look reasonable):
--    AUM should be big numbers (millions+), never tiny ones like 2134.
SELECT MIN(aum_usd) AS smallest_aum, MAX(aum_usd) AS largest_aum, COUNT(aum_usd) AS firms_with_aum
FROM investors;

--    Min ticket should never be bigger than max ticket.
SELECT COUNT(*) AS bad_ticket_ranges
FROM investors
WHERE ticket_size_min_usd > ticket_size_max_usd;
