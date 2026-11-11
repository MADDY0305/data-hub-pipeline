# Investor Warehouse Report

*Final findings of the Data Hub Pipeline, as of 11 Nov 2026.*

We collected investor and firm records from 124 sources, cleaned them, merged duplicates, filled gaps from free public data, and loaded the result into a Postgres warehouse (Supabase) with a SQLite backup. Everything was built with free tools only.

```
Google Sheets · Airtable (OCR) · SEC Form D API · SEC Form ADV · firm websites
   → Extract → Clean & map → De-duplicate → Enrich (fill gaps only) → Load
```

## At a glance

| Metric | Value |
|---|---:|
| Unique investors and firms | **87,215** |
| Contacts (people) | **68,168** (24,679 with email) |
| Investors confirmed by 2+ sources | **23,498** |
| Raw records before de-duplication | 205,870 |
| Sources, each record traceable to its source | 124 |

## What's in the warehouse

**By investor type**

| Type | Investors | Share |
|---|---:|---:|
| Angel | 29,021 | 33.3% |
| Venture Capital | 15,537 | 17.8% |
| Private Equity | 7,815 | 9.0% |
| Other | 5,941 | 6.8% |
| Family Office | 4,758 | 5.5% |
| Corporate VC | 4,332 | 5.0% |
| Multi-Family Office | 3,657 | 4.2% |
| Foundation | 904 | 1.0% |
| Asset Manager | 752 | 0.9% |
| Pension | 735 | 0.8% |
| Fund of Funds | 680 | 0.8% |
| Bank, Accelerator, Endowment, Sovereign Wealth, Hedge Fund, Insurance | 1,192 | 1.4% |
| *No type yet* | 11,891 | 13.6% |

16,217 records (mostly in VC and PE) are SEC Form D fund vehicles ("Fund II, LP"), not management firms. 12,484 investors are marked as investing in funds (LPs).

**Top countries:** United States 31,098 · India 3,839 · United Kingdom 3,520 · China 2,106 · Germany 1,594 · France 966 · Canada 896 · *no country yet* 32,621.

## How complete each field is

Share of the 87,215 investors that have a value:

| Field | Filled |
|---|---:|
| Country | 62.6% |
| City | 54.4% |
| Description | 38.9% |
| Sectors | 33.1% |
| Website | 29.5% |
| Firm phone | 25.4% |
| Stages | 24.6% |
| LinkedIn | 23.5% |
| Firm email | 11.1% |
| AUM (USD) | 5.3% |
| Ticket size | 2.3% |

## What we found

- **De-duplication matters.** 205,870 raw records collapsed into 87,215 investors. The same firm often appears in many lists; one firm was found in 23 sources.
- **Free public data filled real gaps, without overwriting anything.**
  - SEC Form ADV (the US adviser register) enriched 2,957 firms and more than doubled AUM coverage.
  - Firms' own websites (read politely: robots.txt checked, max 2 pages per site, 3 seconds apart) enriched 16,962 investors, and firm emails nearly tripled.
- **Auditing the output caught hidden duplicates.** Angels had been given their *employer's* email domain as a website (for example 11 people at the same bank). After the fix, only 2 investor rows share a website. 720 firms listed under several web addresses were merged, using a rule that only joins websites that look like the firm's name.
- **Blacklists are per client.** 3,327 entries across 31 client funds; 645 investors are flagged. They stay in the data and are excluded per client at query time.

## Known gaps and next steps

| Gap | Idea |
|---|---|
| 32,621 investors have no country (mostly angels) | Infer it from the website ending (`.de`) or phone code (+44) |
| AUM and ticket size are rare in free sources; a few AUM values look too large | Sanity check by firm type (e.g. a family office over $100B) |
| About 5% of names are junk (URLs, file names, phrases) | Stricter name validation in the Transform step |
| 571 same-name rows kept apart on purpose | Manual review; a wrong merge loses data, a missed one only leaves an extra row |
| Not yet checked against an existing company database | Match by website and cleaned name |
| LinkedIn-only sources | Copied in by hand (no automated LinkedIn scraping) |

## The tables

| Table | Rows | Holds |
|---|---:|---|
| `investors` | 87,215 | One row per firm or individual investor: type, location, AUM, sectors, stages, tickets, contact channels, sources |
| `contacts` | 68,168 | People at each investor: name, title, email, phone, LinkedIn |
| `blacklist` | 3,327 | Which investor is blacklisted for which client, and why |
| `sources` | 124 | Every source used, with its link |

Table definitions and practice queries are in [`sql/`](sql/). How each step was built, and the lessons learned along the way, are in [LEARNING_LOG.md](LEARNING_LOG.md).

---
*Built as a learning project with Python, pandas, SQLAlchemy, Supabase (Postgres) and SQLite, all on free tiers. The data itself is not published in this repository.*
