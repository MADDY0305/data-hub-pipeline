"""
dedupe.py - TRANSFORM part 2: merge the same firm from many sources into ONE row.

HOW WE DECIDE TWO RECORDS ARE THE SAME FIRM:
  1. Same website domain          ->  same firm (strongest signal)
  2. No website? Same cleaned name ("Sequoia Capital LLC" = "SEQUOIA CAPITAL")
     -> joined to the website group with that name, but only if there's exactly
        ONE such group and the countries don't clash.
  3. Same name but different countries -> kept apart ("Alpha Capital" UK vs US).

HOW WE PICK THE VALUE FOR EACH FIELD:
  - Most common non-empty value across the merged records ("majority vote").
  - Sectors / stages: combined from all sources, no repeats.
  - source_names: every source the firm appeared in.

Then: people -> contacts table (linked to their firm), and blacklist entries
are matched to firms and flagged per client.

Output (data/clean/):  investors.csv  contacts.csv  blacklist.csv  dedupe_report.txt
Run:  .venv/Scripts/python -m transform.dedupe
"""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from transform.clean import LP_TYPES, firm_key, merge_lists, person_key

OUT = Path("data/clean")
# Fields an enrichment source may fill (investor column -> staging column).
ENRICH_FIELDS = {"website": "website", "country": "country", "city": "city", "address": "address",
                 "aum_usd": "aum_usd", "firm_linkedin": "firm_linkedin", "firm_phone": "firm_phone",
                 "firm_email": "firm_email", "legal_id": "legal_id", "description": "description"}


def majority(values):
    """Most common non-empty value (ties -> the longer one, usually more complete)."""
    vals = [v for v in values if v]
    if not vals:
        return ""
    counts = Counter(vals)
    return max(counts, key=lambda v: (counts[v], len(v)))


def joined(values, sep=" ; ", limit=30):
    out = []
    for v in values:
        if v and v not in out:
            out.append(v)
    return sep.join(out[:limit])


def assign_firm_ids(all_rec: pd.DataFrame) -> pd.Series:
    """Give every staging record a firm number; same number = same firm.
    Main records form the firms; enrichment records may only JOIN a firm."""
    all_rec = all_rec.assign(name_key=all_rec.firm_name.map(firm_key))
    firm_id = pd.Series(-1, index=all_rec.index)
    rec = all_rec[all_rec.is_enrichment != "1"].copy()

    # An individual (e.g. an angel) only joins a website group if a real FIRM
    # has that website - then they're a person at that firm. Otherwise ten
    # people sharing an @bigbank.com email would wrongly become one "investor".
    firm_sites = set(rec.loc[(rec.is_individual != "1") & (rec.website != ""), "website"])
    lone = (rec.is_individual == "1") & ~rec.website.isin(firm_sites)
    rec.loc[lone, "website"] = ""

    # 1) Website groups
    with_site = rec[rec.website != ""]
    site_ids = {d: i for i, d in enumerate(with_site.website.unique())}
    firm_id[with_site.index] = with_site.website.map(site_ids)
    next_id = len(site_ids)

    # Which website groups does each name belong to, and in which countries?
    name_to_sites = with_site.groupby("name_key").website.agg(lambda s: set(s))
    site_country = with_site[with_site.country != ""].groupby("website").country.agg(lambda s: s.mode().iat[0])

    # 2) + 3) Records without a website
    no_site = rec[(rec.website == "") & (rec.name_key != "")]
    for key, grp in no_site.groupby("name_key"):
        sites = name_to_sites.get(key, set())
        if len(sites) == 1:
            site = next(iter(sites))
            c = site_country.get(site, "")
            fits = grp.country.isin(["", c]) if c else pd.Series(True, index=grp.index)
            firm_id[grp[fits].index] = site_ids[site]
            grp = grp[~fits]
        if grp.empty:
            continue
        # Split remaining records by country; ones without a country join the biggest group.
        countries = grp[grp.country != ""].country.value_counts()
        main = countries.index[0] if len(countries) else ""
        for c, sub in grp.groupby(grp.country.where(grp.country != "", main)):
            firm_id[sub.index] = next_id
            next_id += 1

    # 4) Enrichment records: attach to an EXISTING firm or are dropped (-1).
    #    First by website; else by name, if exactly one firm has that name
    #    and the countries don't clash.
    enr = all_rec[all_rec.is_enrichment == "1"]
    main = all_rec.loc[rec.index].assign(firm_id=firm_id[rec.index])
    main = main[main.firm_id >= 0]
    site_to_id = main[main.website != ""].groupby("website").firm_id.first()
    name_to_ids = main[main.name_key != ""].groupby("name_key").firm_id.agg(lambda s: set(s))
    id_country = main[main.country != ""].groupby("firm_id").country.agg(lambda s: s.mode().iat[0])
    for idx, r in enr.iterrows():
        if r.website and r.website in site_to_id.index:
            firm_id[idx] = site_to_id[r.website]
            continue
        ids = name_to_ids.get(r.name_key, set())
        if len(ids) == 1:
            fid = next(iter(ids))
            c = id_country.get(fid, "")
            if not c or not r.country or c == r.country:
                firm_id[idx] = fid
    return firm_id


def build_investors(rec: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for fid, g_all in rec.groupby("firm_id"):
        enrich = g_all[g_all.is_enrichment == "1"]
        g_main = g_all[g_all.is_enrichment != "1"]
        # Firm details come from FIRM records; people at the firm only fill gaps.
        firms_only = g_main[g_main.is_individual != "1"]
        g = firms_only if len(firms_only) else g_main
        firm_type = majority(g.firm_type.replace("Other", "")) or ("Other" if (g.firm_type == "Other").any() else "")
        sources = g_all
        lp_source = g.source_name.str.contains(r"\bLPs?\b|limited partner|fund of fund", case=False).any()
        rows.append({
            "firm_id": fid,
            "firm_name": majority(g.firm_name),
            "firm_type": firm_type,
            "website": majority(g.website),
            "country": majority(g.country),
            "city": majority(g.city),
            "address": majority(g.address),
            "aum_usd": majority(g.aum_usd),
            "sectors": merge_lists(g.sectors),
            "stages": merge_lists(g.stages, limit=8),
            "invests_in_funds": "yes" if (firm_type in LP_TYPES or lp_source) else "unknown",
            "ticket_size_min_usd": majority(g.ticket_min_usd),
            "ticket_size_max_usd": majority(g.ticket_max_usd),
            "firm_linkedin": majority(g.firm_linkedin),
            "firm_email": majority(g.firm_email),
            "firm_phone": majority(g.firm_phone),
            "description": max(g.description, key=len),
            "legal_id": majority(g.legal_id),
            "is_blacklisted": False,
            "in_company_hub": False,
            "source_count": sources.source_name.nunique(),
            "source_names": joined(sources.source_name),
            "source_urls": joined(sources.source_url),
        })
        # ENRICHMENT: only fill fields that are still empty - never overwrite.
        if len(enrich):
            row = rows[-1]
            for field, col in ENRICH_FIELDS.items():
                if not row[field]:
                    row[field] = majority(enrich[col])
    inv = pd.DataFrame(rows)
    # Min and max can come from different sources: if min > max, swap them.
    lo = pd.to_numeric(inv.ticket_size_min_usd, errors="coerce")
    hi = pd.to_numeric(inv.ticket_size_max_usd, errors="coerce")
    flip = lo > hi
    inv.loc[flip, ["ticket_size_min_usd", "ticket_size_max_usd"]] = \
        inv.loc[flip, ["ticket_size_max_usd", "ticket_size_min_usd"]].values
    inv.insert(0, "investor_id", range(1, len(inv) + 1))
    return inv


def build_contacts(rec: pd.DataFrame, fid_to_inv: dict) -> pd.DataFrame:
    ppl = rec[rec.person_name != ""].copy()
    ppl["pkey"] = ppl.person_name.map(person_key)
    rows = []
    for (fid, _), g in ppl.groupby(["firm_id", "pkey"]):
        rows.append({
            "investor_id": fid_to_inv[fid],
            "full_name": majority(g.person_name),
            "title": majority(g.title),
            "email": majority(g.contact_email),
            "phone": majority(g.contact_phone),
            "linkedin": majority(g.contact_linkedin),
            "source_name": joined(g.source_name, limit=5),
        })
    con = pd.DataFrame(rows)
    con.insert(0, "contact_id", range(1, len(con) + 1))
    return con


def match_blacklist(inv: pd.DataFrame, bl: pd.DataFrame, rec: pd.DataFrame) -> pd.DataFrame:
    """Link each blacklist entry to an investor by cleaned name (any name the firm had)."""
    key_to_inv = {}
    names = rec.assign(k=rec.firm_name.map(firm_key))[["k", "investor_id"]].drop_duplicates()
    for k, iid in names.itertuples(index=False):
        if k:
            key_to_inv.setdefault(k, iid)
    bl = bl.copy()
    bl["investor_id"] = bl.firm_name.map(lambda n: key_to_inv.get(firm_key(n)))
    return bl


def main():
    rec = pd.read_csv(OUT / "staging_records.csv", dtype=str).fillna("")
    print(f"Staging records in: {len(rec):,}")
    rec["firm_id"] = assign_firm_ids(rec)
    rec = rec[rec.firm_id >= 0]

    inv = build_investors(rec)
    fid_to_inv = dict(zip(inv.firm_id, inv.investor_id))
    rec["investor_id"] = rec.firm_id.map(fid_to_inv)
    con = build_contacts(rec, fid_to_inv)

    bl = pd.read_csv(OUT / "blacklist_raw.csv", dtype=str).fillna("")
    bl = match_blacklist(inv, bl, rec)
    flagged = set(bl.investor_id.dropna().astype(int))
    inv["is_blacklisted"] = inv.investor_id.isin(flagged)
    inv["last_updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    inv = inv.drop(columns=["firm_id"])

    inv.to_csv(OUT / "investors.csv", index=False)
    con.to_csv(OUT / "contacts.csv", index=False)
    bl.to_csv(OUT / "blacklist.csv", index=False)
    report = (f"Staging records: {len(rec):,}\n"
              f"Unique investors: {len(inv):,}  (merged {len(rec) - len(inv):,} duplicate records)\n"
              f"  found in 2+ sources: {(inv.source_count > 1).sum():,}\n"
              f"Contacts: {len(con):,}  (with email: {(con.email != '').sum():,})\n"
              f"Blacklist entries: {len(bl):,}  matched to an investor: {bl.investor_id.notna().sum():,}\n"
              f"Investors flagged as blacklisted (for at least one client): {inv.is_blacklisted.sum():,}\n"
              f"Investors enriched by SEC Form ADV: "
              f"{inv.source_names.str.contains('SEC Form ADV', regex=False).sum():,}\n"
              f"Investors enriched from their own website: "
              f"{inv.source_names.str.contains('Firm website', regex=False).sum():,}\n")
    (OUT / "dedupe_report.txt").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
