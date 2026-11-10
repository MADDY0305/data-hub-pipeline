"""
load.py - LOAD step: write the clean tables into a database.

DATABASE-INDEPENDENT: the tables are defined ONCE below in Python (SQLAlchemy),
and SQLAlchemy writes the right SQL "dialect" for whichever database you pick.

Pick the target on the command line:
    .venv/Scripts/python -m load.load sqlite      -> data/warehouse.db (local file: test + backup)
    .venv/Scripts/python -m load.load supabase    -> Supabase / PostgreSQL (SUPABASE_DB_URL in .env)
    .venv/Scripts/python -m load.load "<any SQLAlchemy URL>"   e.g. mysql+pymysql://user:pw@host/db

FULL REFRESH (idempotent): each run drops the 4 tables and rebuilds them from
data/clean/*.csv, so running it twice gives exactly the same result.
At the end it counts the rows in the database and compares them with the CSVs.
"""
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import (BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, MetaData, Numeric, Table,
                        Text, create_engine, func, select)

from load.db import get_engine as supabase_engine

CLEAN = Path("data/clean")
SQLITE_URL = "sqlite:///data/warehouse.db"

# ---------------------------------------------------------------------------
# The warehouse tables (matches DATA_DICTIONARY.md)
# ---------------------------------------------------------------------------
meta = MetaData()

investors = Table(
    "investors", meta,
    Column("investor_id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True),
    Column("firm_name", Text, nullable=False),
    Column("firm_type", Text),
    Column("website", Text, index=True),
    Column("country", Text, index=True),
    Column("city", Text),
    Column("address", Text),
    Column("aum_usd", Numeric),
    Column("sectors", Text),
    Column("stages", Text),
    Column("invests_in_funds", Text),
    Column("ticket_size_min_usd", Numeric),
    Column("ticket_size_max_usd", Numeric),
    Column("firm_linkedin", Text),
    Column("firm_email", Text),
    Column("firm_phone", Text),
    Column("description", Text),
    Column("legal_id", Text),
    Column("is_blacklisted", Boolean, default=False),
    Column("in_company_hub", Boolean, default=False),
    Column("source_count", Integer),
    Column("source_names", Text),
    Column("source_urls", Text),
    Column("last_updated", DateTime(timezone=True)),
)

contacts = Table(
    "contacts", meta,
    Column("contact_id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True),
    Column("investor_id", BigInteger, ForeignKey("investors.investor_id", ondelete="CASCADE"), index=True),
    Column("full_name", Text, nullable=False),
    Column("title", Text),
    Column("email", Text),
    Column("phone", Text),
    Column("linkedin", Text),
    Column("source_name", Text),
)

blacklist = Table(
    "blacklist", meta,
    Column("blacklist_id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True),
    Column("firm_name", Text, nullable=False),
    Column("website", Text),
    Column("client", Text, index=True),
    Column("investor_type", Text),
    Column("reason", Text),
    Column("investor_id", BigInteger, ForeignKey("investors.investor_id", ondelete="SET NULL"), index=True),
    Column("source_name", Text),
    Column("source_url", Text),
)

sources = Table(
    "sources", meta,
    Column("source_id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True),
    Column("source_name", Text, nullable=False),
    Column("url", Text),
    Column("method", Text),
    Column("status", Text),
    Column("records_extracted", Integer),
    Column("notes", Text),
)


# ---------------------------------------------------------------------------
# Reading the clean CSVs and fixing types for the database
# ---------------------------------------------------------------------------
def read_csv(name):
    df = pd.read_csv(CLEAN / name, dtype=str, keep_default_na=False)
    return df.replace({"": None})             # empty text -> real NULL in the database


def as_number(s):
    return pd.to_numeric(s, errors="coerce").astype(object).where(lambda x: pd.notna(x), None)


def as_bool(s):
    return s.map(lambda v: str(v).lower() in ("true", "1", "yes"))


def prepare():
    inv = read_csv("investors.csv")
    for col in ("aum_usd", "ticket_size_min_usd", "ticket_size_max_usd", "investor_id", "source_count"):
        inv[col] = as_number(inv[col])
    for col in ("is_blacklisted", "in_company_hub"):
        inv[col] = as_bool(inv[col])
    inv["last_updated"] = pd.to_datetime(inv["last_updated"], utc=True)

    con = read_csv("contacts.csv")
    con[["contact_id", "investor_id"]] = con[["contact_id", "investor_id"]].apply(as_number)

    bl = read_csv("blacklist.csv")
    bl["investor_id"] = as_number(bl["investor_id"])
    bl.insert(0, "blacklist_id", range(1, len(bl) + 1))
    bl = bl[[c.name for c in blacklist.columns]]

    # Sources table: one row per source we actually extracted from.
    rec = pd.read_csv(CLEAN / "staging_records.csv", dtype=str, keep_default_na=False,
                      usecols=["source_name", "source_url", "source_file"])
    src = (rec.groupby("source_name")
              .agg(url=("source_url", "first"), records_extracted=("source_file", "size"),
                   file=("source_file", "first")).reset_index())
    src["method"] = src.file.map(lambda f: "SEC API" if f.startswith("form_d") else
                                 "PDF + OCR" if f[:-4].isdigit() else
                                 "Airtable CSV" if "Grid view" in f else "Google Sheets API")
    src["status"] = "done"
    src["notes"] = None
    src.insert(0, "source_id", range(1, len(src) + 1))
    src = src[[c.name for c in sources.columns]].replace({"": None})
    return {"investors": inv, "contacts": con, "blacklist": bl, "sources": src}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def pick_engine(target: str):
    if target == "sqlite":
        Path("data").mkdir(exist_ok=True)
        return create_engine(SQLITE_URL)
    if target == "supabase":
        return supabase_engine()
    return create_engine(target)


def copy_into_postgres(engine, name, df, chunk=5000):
    """PostgreSQL's bulk loader (COPY): streams rows as CSV text - far faster
    than one INSERT per row over the internet. Sent in chunks; each chunk is
    saved (committed) on its own and retried if the connection drops."""
    import csv
    import io
    import time

    import psycopg2

    cols = ", ".join(df.columns)
    sql = f"COPY {name} ({cols}) FROM STDIN WITH (FORMAT csv, NULL '\\N')"
    # Turn values into the text COPY expects: NULL -> \N, True -> true, dates -> ISO text.
    text = df.astype(object).where(df.notna(), "\\N")
    text = text.map(lambda v: "true" if v is True else "false" if v is False else
                    v.isoformat() if hasattr(v, "isoformat") else
                    int(v) if isinstance(v, float) and v.is_integer() else v)   # 42258.0 -> 42258
    for start in range(0, len(text), chunk):
        part = text.iloc[start:start + chunk]
        buf = io.StringIO()
        part.to_csv(buf, index=False, header=False, quoting=csv.QUOTE_MINIMAL)
        for attempt in range(4):
            raw = engine.raw_connection()
            try:
                buf.seek(0)
                with raw.cursor() as cur:
                    cur.copy_expert(sql, buf)
                raw.commit()
                break
            except psycopg2.OperationalError:
                raw.close()
                if attempt == 3:
                    raise
                time.sleep(5 * (attempt + 1))   # connection dropped: wait, retry this chunk
            finally:
                try:
                    raw.close()
                except Exception:
                    pass
        print(f"    {name}: {min(start + chunk, len(text)):,}/{len(text):,}", flush=True)


def load(target: str):
    engine = pick_engine(target)
    data = prepare()
    print(f"Target: {engine.dialect.name}")

    # 1) Full refresh: drop old tables (children first), create fresh ones.
    with engine.begin() as conn:
        meta.drop_all(conn)
        meta.create_all(conn)
    print("  tables rebuilt")

    # 2) Insert, parents before children (contacts point at investors).
    for name in ("investors", "contacts", "blacklist", "sources"):
        df = data[name]
        if engine.dialect.name == "postgresql":
            copy_into_postgres(engine, name, df)          # fast bulk path
        else:
            chunk = max(100, 30000 // len(df.columns))    # stay under per-INSERT limits
            with engine.begin() as conn:
                df.to_sql(name, conn, if_exists="append", index=False, method="multi", chunksize=chunk)
        print(f"  {name:10} {len(df):>8,} rows written")

    # 3) Verify: count what's really in the database.
    ok = True
    with engine.connect() as conn:
        for name, df in data.items():
            n = conn.execute(select(func.count()).select_from(meta.tables[name])).scalar()
            match = "OK" if n == len(df) else "MISMATCH"
            ok &= n == len(df)
            print(f"  check {name:10} database={n:>8,}  csv={len(df):>8,}  {match}")
    print("LOAD COMPLETE" if ok else "LOAD FINISHED WITH MISMATCHES - see above")


if __name__ == "__main__":
    load(sys.argv[1] if len(sys.argv) > 1 else "sqlite")
