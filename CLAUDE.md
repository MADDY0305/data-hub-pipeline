# CLAUDE.md — Rules for this project

## What this project is
An ETL pipeline that collects investor/firm records (LPs, family offices, VCs, PE, funds-of-funds) from the sources in `Data_sources_Notion_export.xlsx`, cleans and enriches them, and loads them into a Supabase (Postgres) data warehouse.

## Who I'm working with
The project owner is **new to data engineering** and wants to learn it.
- Explain things in short, plain English. No unexplained jargon.
- Comment code in plain English (what it does and why).
- Put every SQL query in its own `.sql` file under `sql/`, with comments, so the owner can run and study it.

## Hard rules
1. **Free only.** Never pay for anything and never suggest paid plans. With paid providers, use only free tiers, public pages, previews, and samples.
2. **No paywall or login bypassing**, no CAPTCHA solving, no account sharing. Respect robots.txt and the site's Terms of Service. Rate-limit every scraper (≥2–3 seconds between requests).
3. **No automated LinkedIn scraping.** The owner copies post content and I parse it.
4. **Never handle passwords.** The owner creates accounts and logs in. Secrets live only in `.env`, which is git-ignored and never printed or committed.
5. **Blacklists are per client** (each sheet is named after a client fund). Blacklisted investors stay in `investors` with `is_blacklisted = true`; the `blacklist` table says which client and why. Exclude them per client at query time.
6. **Check duplicates** against the company's existing investor database (~35k investors) and within our own data.
7. Every record keeps `source_name` + `source_url` so it can be traced.

## Data-gathering order (when a source has no free API)
1. Free bulk download or CSV export
2. Free public API
3. Scrape public web pages (requests + BeautifulSoup; Playwright if the page needs JavaScript)
4. Free-tier account the owner logs into → export, or browse in the built-in browser
5. Owner copies/pastes or screenshots → I parse
6. Find the same data from another free source

## Folder layout (planned)
```
extract/      one script per source type (gsheets, airtable, sec, web, manual)
transform/    cleaning, standardising, de-duplication, enrichment
load/         writes to Supabase
sql/          table definitions and queries (commented, for learning)
data/raw/     untouched downloads (git-ignored)
data/clean/   cleaned output (git-ignored)
docs/         the .md documentation
```

## Field names
Use the exact column names in `DATA_DICTIONARY.md`. Don't invent new ones without updating that file.
