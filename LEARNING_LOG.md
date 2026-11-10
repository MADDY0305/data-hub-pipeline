# LEARNING LOG — what we did and why (plain English)

Your study notes. Each step says **what** we did, **why**, the **concept** (the data-engineering word for it), and a **you-try** exercise.

---

## Step 1 — Inventory the sources
**What:** Read the Notion export (~1,000 rows, ~507 real) and grouped it: 186 LinkedIn posts, 151 Google Sheets, 19 Airtable links, 29 public registers, ~73 paid providers, 32 blacklists.
**Why:** You can't plan extraction until you know what kinds of sources you have. Each kind needs a different method.
**Concept:** *Source inventory / data discovery.*
**Lesson learned:** The inventory had duplicates (the same link under 2 names) and misleading names (the word "Airtable" appeared only inside links). Always look at the data itself, not just the labels.

## Step 2 — Choose free tools
**What:** Python (code), VS Code (editor), Git (version history), Supabase (database), Google Cloud (Sheets access), OCR (reads text from images).
**Why:** Everything had to cost $0.
**Concept:** *Tech stack.*

## Step 3 — Keep secrets safe
**What:** Passwords and keys live in `.env` and in key files. `.gitignore` stops them from being uploaded.
**Why:** A leaked key = anyone can use your accounts. (The Airtable token was pasted in chat, so it should be regenerated.)
**Concept:** *Secrets management.*
**You-try:** Open `.gitignore`. Read each line and say why it's there.

## Step 4 — Build the warehouse (SQL)
**What:** Created 4 tables in Supabase: `investors`, `contacts`, `blacklist`, `sources`. Then added a `client` column to `blacklist` with `ALTER TABLE`.
**Why:** The final, clean data needs a fixed shape (a *schema*) so everyone queries it the same way.
**Concept:** *Data warehouse, schema, primary key, foreign key (contacts → investors).*
**You-try:** In the Supabase SQL Editor, run `SELECT * FROM blacklist;`, and then `SELECT column_name FROM information_schema.columns WHERE table_name = 'investors';`

## Step 5 — Connect code to the database
**What:** `load/db.py` builds the connection link from `.env`.
**Problem we hit:** The password had an `@`, which broke the link (`user:pass@host`). We fixed it by "escaping" the password (`@` becomes `%40`).
**Concept:** *Connection string, URL encoding.*

## Step 6 — Extract: Airtable
**What:** The API couldn't read other people's bases (a token sees only your own). Some links allowed CSV download; most only allowed **Print**. You printed them to PDF.
**Problem we hit:** The PDFs had no real text, only drawn shapes.
**Fix:** **OCR**. `extract/airtable_pdf_ocr.py` (1) finds the table grid, (2) reads the text and its position on the page, (3) puts each word into the right cell.
**Concept:** *Unstructured → structured data, OCR.*
**Lesson learned:** The best source is the one closest to the original. A CSV beats a PDF, which beats a screenshot.

## Step 7 — Extract: Google Sheets
**What:** First we checked access to all 151 sheets.
- With a **service account** (robot): 18 opened. The rest are "company-only" sharing, and the robot isn't in the company.
- With **OAuth** (logging in as *you*, read-only): 86 opened. The other 65 are deleted or private even for you.

Then `extract/gsheets_extract.py` saved **every tab** of the 86 as its own untouched CSV: 166 tabs, ~462k rows.
**Why untouched:** That's the *raw layer*. If we clean something wrongly later, we can always start over from raw.
**Concept:** *Authentication (service account vs OAuth), API rate limits (we pause about 1 second between requests), raw/landing zone, manifest (an index of what was extracted).*
**You-try:** Open `data/raw/gsheets/manifest.csv` in Excel. Sort by `rows`. Which source is the biggest?

## Step 8 — Extract from a real API: SEC EDGAR (Form D)
**What:** US funds raising money must file "Form D". `extract/sec_form_d.py` uses two free SEC endpoints:
1. **Search API**: "every Form D mentioning 'Venture Capital Fund' in March". Results come back as **JSON**, 100 per **page**.
2. **Archive**: downloads each filing as **XML** (text with `<tags>`), saves it raw, then reads out the fund name, address, phone, type, amount raised and people.

**Problems we hit (and fixes):**
- The filter `forms=D,D/A` returned only amendments. Testing showed plain `D` returns both. *Lesson: test your assumptions on a small sample.*
- Too many fast, new connections made the SEC refuse us, and 270 downloads were skipped. Fix: reuse one connection (a **session**), go slower (5 per second), and **retry with growing waits** (*backoff*).
- A search can return at most 10,000 results, so we search **one month at a time**.

**Concepts:** *REST API, JSON vs XML, pagination, rate limiting, retry and backoff, User-Agent header.*
**You-try:** Open https://efts.sec.gov/LATEST/search-index?q=%22Venture%20Capital%20Fund%22&forms=D in your browser. That's the raw JSON the code reads.

## Step 9 — Transform: from ~185 messy files to 3 clean tables
Four scripts in `transform/`, each doing one job:

| Script | Job | Example |
|---|---|---|
| `clean.py` | Fix ONE kind of value | `HTTPS://www.Abc.com/x` → `abc.com`; `USA` → `United States` |
| `mapping.py` | Work out what each column MEANS | `Investor Name`, `Firm`, `company_name` → `firm_name` |
| `stage.py` | Every row from every source → one standard record | 140k records, same columns |
| `dedupe.py` | Merge the same firm and pick the best values | 140k records → ~76k investors |

**How duplicates are found:** same website, then same cleaned name (`Sequoia Capital, L.P.` = `SEQUOIA CAPITAL LLC`). The same name in different countries stays separate.

**Bugs we found by LOOKING at the output (the most important habit!):**
- 29k "firm names" were really emails, because one sheet had shifted columns. *Fix:* detect the `@` and move the value to the email column.
- "Sequoia Capital" was typed as "Angel", because people with @sequoiacap.com emails were treated as firms. *Fix:* individuals become **contacts** of the firm and never override its details.
- `hotmail.co.uk` was treated as a company website. *Fix:* a wider free-email list.
- `Alex Leibowitz Vice President at Insight`. *Fix:* split it into name and title.
- An invisible character (`﻿`, a "BOM") hid the `Name` column of 2 files.

**Concepts:** *schema mapping, data cleaning/standardisation, entity resolution (de-duplication), "majority vote" (survivorship rules), data profiling, staging layer.*
**You-try:** Open `data/clean/column_mapping_report.csv` and find one file where you'd map a column differently.

## Step 10 — Decision: which database to LOAD into (planned)
**Question we asked:** What if we want a different database later, like PostgreSQL, SQLite or MySQL?

**Facts first:**
- **Supabase IS PostgreSQL**, just hosted online for us. So we already use Postgres.
- **SQLite** = a whole database in **one file** on your PC. No server, no login. Great for testing and backups.
- **MySQL / SQL Server** = other popular databases. They need extra drivers and setup.

**The problem:** each database speaks a slightly different **SQL dialect**. Our `sql/001_create_tables.sql` uses Postgres-only words (`BIGSERIAL`, `TIMESTAMPTZ`), so it won't run on SQLite.

**The solution: database-independent code with SQLAlchemy.**
- SQLAlchemy is a free Python library that talks to almost every database.
- We define the tables **once, in Python**, and SQLAlchemy writes the right SQL dialect for each database.
- The database is picked by **one line in `.env`**:
  ```
  DATABASE_URL=postgresql://...              # Supabase (main)
  DATABASE_URL=sqlite:///data/warehouse.db   # local file
  DATABASE_URL=mysql+pymysql://...           # MySQL (if ever needed)
  ```
  Switching databases = changing that line, not rewriting code.

**What we decided:**
| Role | Database | Why |
|---|---|---|
| Main warehouse | **Supabase (PostgreSQL)** | Free, online, web UI for the team, industry standard |
| Test + backup | **SQLite** | Every load is tried locally first; a full offline copy in one file |
| Not now | MySQL / SQL Server | Nobody needs them yet; would add setup for no benefit |

**Two more design rules for Load:**
1. **Idempotent:** every run *replaces* the tables with the latest clean data. Running it twice never creates duplicates. That's why we didn't have to wait for the SEC download: when it finishes, we just re-run Transform and then Load.
2. **Test before production:** load into SQLite, check the counts, *then* load into Supabase.

**Concepts:** *SQL dialects, ORM / database abstraction (SQLAlchemy), connection string, idempotent loads, test vs production environment, full refresh (replace everything) vs incremental load (add only what's new).*
**You-try:** Once SQLite is loaded, install the free app "DB Browser for SQLite", open `data/warehouse.db`, and run `SELECT COUNT(*) FROM investors;`

## Step 11 — Load (done)
**What:** `load/load.py` defines the 4 tables once in Python (SQLAlchemy), drops and rebuilds them (*full refresh*), inserts the clean CSVs, then **counts the rows in the database and compares them with the CSVs**.
- **SQLite test:** 50 seconds, all counts matched. The file is `data/warehouse.db` (45 MB).
- **Supabase, first try:** failed after 9 minutes with "server closed the connection". Sending thousands of small `INSERT`s over the internet was too slow for the free connection.
- **Fix:** Postgres's bulk loader, **`COPY`**, which streams CSV text in chunks of 5,000 rows, each saved on its own and retried if the connection drops. Result: **2.5 minutes**, all counts matched.
- **Small bug:** an ID went out as `42258.0` (decimal) into a whole-number column. Empty values make pandas store numbers as decimals. *Fix:* convert `42258.0` to `42258`.

**Concepts:** *bulk load (COPY) vs row inserts, transactions/commits, chunking, data types, post-load verification (row-count reconciliation).*
**You-try:** Run the queries in `sql/003_example_queries.sql` in the Supabase SQL Editor. Then change query 6 to a different client and country.

---

## The pipeline so far
```
EXTRACT   ✅ Google Sheets (86)  ✅ Airtable OCR (16)  ⏳ SEC API  ⬜ LinkedIn, registers, websites
TRANSFORM ✅ map columns → clean → de-duplicate → flag blacklist (71,754 investors, 40,014 contacts)
LOAD      ✅ SQLite (test/backup) + Supabase (main): 71,754 investors, 40,014 contacts, 3,327 blacklist rows
```

## Words to know
| Word | Meaning |
|---|---|
| ETL | Extract, Transform, Load: get data, fix it, store it |
| Raw layer | Untouched copies of the source data |
| Schema | The fixed set of columns and types a table has |
| API | A door that lets code ask a service for data |
| OAuth | "Log in as me" for code, with limited permissions |
| Rate limit | Max requests per minute a service allows |
| OCR | Reading text from an image |
| Idempotent | Safe to re-run: running twice gives the same result, no duplicates |
| SQL dialect | Each database's own flavour of SQL |
| SQLAlchemy | Python library that talks to any database |
| Connection string | The "address + login" of a database, in one line |
| Entity resolution | Working out which records are the same real-world firm |
