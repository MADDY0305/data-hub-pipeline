-- =====================================================================
-- 003_example_queries.sql - practice queries on the loaded warehouse.
-- HOW TO RUN: Supabase -> SQL Editor -> paste ONE query -> Run.
-- (Works on the SQLite copy too: data/warehouse.db in "DB Browser for SQLite".)
-- Note: the tables are now created by load/load.py, so 001/002 are just
-- for learning - load.py rebuilds the tables on every run.
-- =====================================================================


-- 1) How many investors of each type?   (GROUP BY = "count per group")
SELECT firm_type, COUNT(*) AS investors
FROM investors
GROUP BY firm_type
ORDER BY investors DESC;


-- 2) Family offices in Germany with a website.   (WHERE = filter rows)
SELECT firm_name, website, city
FROM investors
WHERE firm_type = 'Family Office'
  AND country = 'Germany'
  AND website IS NOT NULL
ORDER BY firm_name;


-- 3) Likely LPs (invest in funds) in the UAE or Saudi Arabia.   (IN = one of a list)
SELECT firm_name, firm_type, country, website
FROM investors
WHERE invests_in_funds = 'yes'
  AND country IN ('United Arab Emirates', 'Saudi Arabia');


-- 4) Firms found in the MOST sources (= most widely known).
SELECT firm_name, source_count, website
FROM investors
ORDER BY source_count DESC
LIMIT 20;


-- 5) People at a firm, with emails.   (JOIN = combine two tables on a shared ID)
SELECT i.firm_name, c.full_name, c.title, c.email
FROM contacts c
JOIN investors i ON i.investor_id = c.investor_id
WHERE i.firm_name = 'Accel'
ORDER BY c.full_name;


-- 6) Prospect list for a client, EXCLUDING that client's blacklist.
--    (NOT EXISTS = "and there's no matching row in the other table")
SELECT i.firm_name, i.firm_type, i.country, i.website
FROM investors i
WHERE i.firm_type IN ('Family Office', 'Multi-Family Office', 'Fund of Funds')
  AND i.country = 'United States'
  AND NOT EXISTS (
        SELECT 1 FROM blacklist b
        WHERE b.investor_id = i.investor_id
          AND b.client = 'Client A'   -- see clients: SELECT DISTINCT client FROM blacklist;
  )
LIMIT 100;


-- 7) Which clients' blacklists are biggest?
SELECT client, COUNT(*) AS entries, COUNT(investor_id) AS matched_to_our_investors
FROM blacklist
GROUP BY client
ORDER BY entries DESC;


-- 8) Data quality: how complete is each field?  (COUNT(column) skips empty values)
SELECT COUNT(*)              AS total,
       COUNT(website)        AS with_website,
       COUNT(country)        AS with_country,
       COUNT(firm_linkedin)  AS with_linkedin,
       COUNT(aum_usd)        AS with_aum
FROM investors;


-- 9) Where did our data come from?
SELECT method, COUNT(*) AS sources, SUM(records_extracted) AS records
FROM sources
GROUP BY method
ORDER BY records DESC;
