# Data Hub Pipeline

Collects investor and firm data from 500+ free and public sources, cleans it, fills in missing details, removes duplicates and blacklisted firms, and stores the result in one database.

```
Sources (Sheets, Airtable, registers, websites, LinkedIn posts)
      │  EXTRACT  – pull the raw data
      ▼
data/raw/
      │  TRANSFORM – clean, standardise, de-duplicate, enrich
      ▼
data/clean/
      │  LOAD – write into the warehouse
      ▼
Supabase (Postgres)  →  query with SQL
```

## Docs
| File | Read it for |
|---|---|
| [REPORT.md](REPORT.md) | **Final findings: what's in the warehouse and how complete it is** |
| [PIPELINE_PLAN.md](PIPELINE_PLAN.md) | The big picture: tools, roles, roadmap |
| [SETUP.md](SETUP.md) | One-time setup: accounts and keys |
| [DATA_DICTIONARY.md](DATA_DICTIONARY.md) | What every column means |
| [CLAUDE.md](CLAUDE.md) | Project rules (free only, no scraping LinkedIn, etc.) |

## How to run
Open a terminal in this folder. Each step can be re-run safely.

**1. Extract** (only when sources change)
```bash
.venv/Scripts/python -m extract.gsheets_check_access
```
```bash
.venv/Scripts/python -m extract.gsheets_extract
```
```bash
.venv/Scripts/python -m extract.sec_form_d 2026-01-01 2026-10-31
```
```bash
.venv/Scripts/python extract/airtable_pdf_ocr.py
```

**2. Transform**
```bash
.venv/Scripts/python -m transform.stage
```
```bash
.venv/Scripts/python -m transform.dedupe
```

**3. Load** (test locally first, then the real warehouse)
```bash
.venv/Scripts/python -m load.load sqlite
```
```bash
.venv/Scripts/python -m load.load supabase
```

Practice queries: [sql/003_example_queries.sql](sql/003_example_queries.sql)

## Cost
$0. Every tool and service is free, or a free tier.
