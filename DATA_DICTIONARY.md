# DATA DICTIONARY — what every column means

> **Status: DRAFT.** Waiting for the owner's approval. Edit freely: add, remove, or rename columns.

## Table: `investors` (the main output: one row per firm)

| Column | Meaning | Format | Example |
|---|---|---|---|
| `investor_id` | Our unique ID for the firm | number (auto) | 1042 |
| `firm_name` | Official firm name | text | Walton Family Office |
| `firm_type` | Kind of investor | one of: Family Office, Multi-Family Office, VC, PE, Fund of Funds, Pension, Endowment, Foundation, Insurance, Sovereign Wealth, Corporate VC, Angel, Other | Family Office |
| `website` | Main website | URL, lowercase, no trailing slash | https://example.com |
| `country` | HQ country | full English name | United States |
| `city` | HQ city | text | New York |
| `address` | HQ street address | text | 1 Main St, NY 10001 |
| `aum_usd` | Assets under management | number in USD | 500000000 |
| `sectors` | Sectors they invest in | comma list | AI, Fintech, Healthcare |
| `stages` | Stages they invest in | comma list | Seed, Series A |
| `invests_in_funds` | Do they back VC/PE funds (i.e. are they an LP)? | yes / no / unknown | yes |
| `ticket_size_min_usd` | Smallest typical investment | number in USD | 250000 |
| `ticket_size_max_usd` | Largest typical investment | number in USD | 5000000 |
| `firm_linkedin` | Firm's LinkedIn page | URL | https://linkedin.com/company/... |
| `firm_email` | General email | email | info@example.com |
| `firm_phone` | Main phone | +country code | +1 212 555 0100 |
| `legal_id` | Registry or LEI number | text | LEI 5493001KJTIIGC8Y1R12 |
| `description` | What the firm does / its thesis (longest one found) | text | Early-stage fund backing B2B SaaS |
| `is_blacklisted` | On at least one client's blacklist? | yes / no | no |
| `source_count` | How many different sources list this firm | number | 4 |
| `in_company_hub` | Already in the company's existing investor database? | yes / no | no |
| `source_names` | Every source this firm came from | comma list | SEC EDGAR, 330+ US Family Offices |
| `source_urls` | Links to those sources | comma list | https://... |
| `last_updated` | When the pipeline last touched this row | date-time | 2026-11-04 18:00 |

## Table: `contacts` (people at each firm: many per firm)

| Column | Meaning | Format | Example |
|---|---|---|---|
| `contact_id` | Our unique ID | number (auto) | 88 |
| `investor_id` | Which firm they work at | links to `investors` | 1042 |
| `full_name` | Person's name | text | Jane Doe |
| `title` | Job title | text | Chief Investment Officer |
| `email` | Work email | email | jane@example.com |
| `phone` | Direct phone | +country code | +1 212 555 0101 |
| `linkedin` | Personal LinkedIn | URL | https://linkedin.com/in/... |
| `source_name` | Where we found them | text | LN Harvey Knight – 20 FOs |
| `last_updated` | Last touched | date-time | 2026-11-04 18:00 |

## Table: `blacklist` (per client)
The 32 blacklists are named after client funds, so an entry means "don't use this investor **for that client**". The investor stays in `investors`.

| Column | Meaning |
|---|---|
| `firm_name` | Investor on the list |
| `website` | Its website, if known (helps matching) |
| `client` | Client fund whose list it's on (e.g. Client A) |
| `investor_id` | Matching row in `investors`, once matched |
| `reason` | Why, if known |
| `source_name` | Which blacklist sheet it came from |

`investors.is_blacklisted` = on **at least one** client's list.

## Contacts
Kept, and filled **only when a source has them**. Firms with no contact are fine.

## Table: `sources` (tracks our ~507 sources)
| Column | Meaning |
|---|---|
| `source_name`, `url` | From the Notion export |
| `method` | api / bulk download / scrape / free-tier login / manual |
| `status` | not started / in progress / done / blocked |
| `records_extracted` | How many rows we got |
| `notes` | Problems, limits, etc. |
