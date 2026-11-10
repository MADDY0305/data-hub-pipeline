# Investor Data Pipeline — Plan (100% free)

## What we're building (plain English)
1. **Extract** – pull investor/firm records out of each source (sheets, websites, registers, posts).
2. **Transform** – clean them, put them in one standard format, remove duplicates, fill gaps (website, AUM, contacts, LinkedIn…).
3. **Load** – save the final clean table into a free online database ("data warehouse") the team can query.

## What's in your source file
~507 real sources (the other ~490 rows are empty):

| Kind | Count | How we get the data |
|---|---|---|
| LinkedIn posts (lists of FOs/VCs) | 186 | You open/copy them; I parse. (Auto-scraping LinkedIn breaks their rules and can get the account banned.) |
| Google Sheets | 91 | Automatic, via the free Google Sheets API |
| Airtable bases | 22 | Automatic, via the Airtable API |
| Public registers (SEC, ASIC, KVK…) | 29 | Automatic where there's a free API/bulk download (SEC, GLEIF); semi-manual elsewhere |
| Data providers / platforms | 47 | Free tier or free pages only |
| Paid sources | ~73 | Only what's visible for free (previews, samples, free tiers). No paying, no paywall bypassing. |
| Blacklists | 32 | Loaded so we can **exclude** those firms |
| News / newsletters / events | ~50 | Low priority; manual |

## 1. Tools (all free)

| # | Tool | What it's for |
|---|---|---|
| 1 | **VS Code** | Where code files are opened/edited |
| 2 | **Python 3.13** (already on your PC) | Language the pipeline is written in |
| 3 | **Claude Code** (this app) | Writes and runs the code |
| 4 | **Git + GitHub** (free account) | Saves code history; runs the pipeline on a schedule |
| 5 | **GitHub Actions** | Free scheduler (e.g. run every night) |
| 6 | **Supabase** (free tier, Postgres) | **The data warehouse** — 500 MB free, easy web UI, plenty for ~50k investors |
| 7 | **Google Cloud project** (free) | Gives an API key to read Google Sheets/Drive |
| 8 | **Airtable** (existing account) | Personal access token to read bases |
| 9 | **Google Chrome** | Manual sign-ups and copying LinkedIn posts |
| 10 | Python libraries: `pandas`, `requests`, `beautifulsoup4`, `playwright`, `openpyxl`, `gspread`, `rapidfuzz`, `sqlalchemy`, `psycopg2`, `python-dotenv` | Reading files, websites, sheets; fuzzy de-duplication; writing to the database |
| 11 | Free data APIs: **SEC EDGAR**, **GLEIF (LEI)**, **OpenCorporates** (free tier) | Enrich firms with legal name, address, registration, filings |
| 12 | `.env` file (local, never uploaded) | Stores API keys safely |

### Requirements checklist
- [ ] GitHub account
- [ ] Supabase account + one project
- [ ] Google Cloud project with Sheets + Drive API on, a "service account" key, and the source sheets shared with it
- [ ] Airtable personal access token (read-only)
- [ ] VS Code installed
- [ ] The **target fields** you want filled for each investor (draft below — confirm or edit)

### Draft output fields
Firm name · Type (FO / VC / PE / Fund-of-funds / Pension / Angel…) · Website · Country · City · HQ address · AUM · Investment focus (sectors, stages) · Ticket size · Contact name · Title · Email · Phone · LinkedIn (firm) · LinkedIn (person) · Source(s) · Source URL · Last updated · Blacklisted (yes/no)

## 2. Skills you need (minimal)
You do **not** need to code. Useful to learn, in this order:
1. **Basic spreadsheet sense** – columns, rows, duplicates. (You have this.)
2. **Copy/paste into a terminal & run one command** – I'll give you exact commands.
3. **Creating accounts & API keys** – I'll walk you through each click.
4. **Reading a table in Supabase** – to check results.
5. (Optional, later) Very basic SQL: `SELECT * FROM investors WHERE country = 'USA'`.

## 3. Who does what

| Task | Claude | You |
|---|---|---|
| Design the database tables & fields | ✅ | Approve |
| Write all pipeline code (extract, clean, dedupe, enrich, load) | ✅ | |
| Run & test the code on your PC | ✅ | |
| Pull Google Sheets / Airtable / SEC / GLEIF data | ✅ (once keys exist) | |
| Parse LinkedIn posts / PDFs / images you give me | ✅ | |
| Check new records against the company's existing investor database (~35k) for duplicates | ✅ | |
| Create accounts (GitHub, Supabase, Google Cloud, data sites) | | ✅ |
| Generate API keys and paste them into the `.env` file | | ✅ |
| Log in to sites, solve CAPTCHAs, accept terms | | ✅ |
| Open LinkedIn posts and copy their content/attachments | | ✅ |
| Decide priorities & approve the final field list | | ✅ |
| Spot-check final data quality | ✅ first pass | ✅ final OK |

## 4. Sign-ups & your Gmail password
**Please don't send me your Gmail password.** For safety I'm not allowed to type passwords or create accounts. Instead:
- You sign up yourself (2 minutes per site).
- If you sign in inside this app's built-in browser, I can then browse those sites for you while you stay logged in.
- API keys go into the `.env` file on your PC — not into chat.

## Suggested order of work
1. Week 1 – Accounts + keys (you), database + code skeleton (me).
2. Week 1–2 – Easy wins: 91 Google Sheets + 22 Airtable bases + blacklists → warehouse.
3. Week 2 – Free APIs (SEC, GLEIF) to enrich firms.
4. Week 3 – LinkedIn posts & free-tier providers (you copy, I parse).
5. Ongoing – nightly automatic refresh via GitHub Actions.
