"""
stage.py - TRANSFORM part 1: turn every raw file into ONE standard table.

For each usable file: find its header -> give each column a role (mapping.py)
-> clean every value (clean.py) -> write one "record" per row with the SAME
columns for every source. Nothing is merged yet; that's dedupe.py.

Sources read:
  data/raw/gsheets/files/*.csv   Google Sheets tabs   (blacklists handled separately)
  data/raw/airtable/ocr/*.csv    Airtable PDFs read by OCR
  data/raw/airtable/*.csv        Airtable CSV downloads
  data/raw/sec/form_d_*.csv      SEC Form D API data

Output:
  data/clean/staging_records.csv   one row per source row
  data/clean/blacklist_raw.csv     every blacklist entry with its client
  data/clean/stage_report.csv      per file: used/skipped, rows in/out
Run:  .venv/Scripts/python -m transform.stage
"""
import csv
import difflib
import glob
import os
import re
from pathlib import Path

import openpyxl
import pandas as pd

from transform.clean import (clean_country, clean_email, clean_firm_type, clean_linkedin, clean_money,
                             clean_name, clean_phone, clean_text, clean_website, city_from_text,
                             country_from_text, email_domain, money_range, person_key, split_name_headline)
from transform.mapping import map_columns, read_table, skip_reason

OUT = Path("data/clean")
NOTION_EXPORT = Path.home() / "Downloads" / "Data_sources_Notion_export.xlsx"
RECORD_COLUMNS = [
    "source_name", "source_url", "source_file",
    "firm_name", "firm_type", "website", "country", "city", "address", "aum_usd",
    "sectors", "stages", "ticket_min_usd", "ticket_max_usd", "firm_linkedin", "firm_email",
    "firm_phone", "description", "legal_id",
    "is_individual", "person_name", "title", "contact_email", "contact_phone", "contact_linkedin",
    "is_enrichment",   # "1" = only fills gaps in firms we already have; never adds a new firm
]
MONEY_ROLES = {"aum", "ticket", "ticket_min", "ticket_max"}


def header_unit(header: str) -> str:
    """Unit written in a column header -> text to append to each value."""
    h = header.lower()
    if re.search(r"\b(bn|billion|billions|\$b)\b|\(b\)", h):
        return " billion"
    if re.search(r"\b(mn|mm|mio|million|millions|\$m)\b|\(m\)|\(usd m\)|\(eur m\)", h):
        return " million"
    if re.search(r"\b(k|thousand|thousands|\$k)\b|\(k\)", h):
        return " thousand"
    return ""


def email_fits_person(email: str, person: str, firm_site: str) -> bool:
    """Does this email plausibly belong to this person (or their firm)?
    'maurice@souterinvestments.com' fits 'Maurice Shamash'; 'jesse.cordoba@x.com'
    does NOT fit 'Jonas Agrup'. Generic firm mailboxes on the firm's domain fit too."""
    local, _, domain = email.partition("@")
    if firm_site and (domain == firm_site or domain.endswith("." + firm_site)):
        return True
    letters = re.sub(r"[^a-z]", "", local.lower())
    names = [n for n in re.sub(r"[^a-z ]", " ", person_key(person)).split() if len(n) >= 2]
    if not names or not letters:
        return False
    first, last = names[0], names[-1]
    return (any(len(n) >= 3 and n in letters for n in names)          # 'maurice', 'shamash'
            or (len(letters) >= 3 and letters[0] == first[0]          # 'tom' -> 'thomas'
                and re.search(".*".join(map(re.escape, letters)), first) is not None)
            or letters in (first[0] + last, first + last[0], first[0] + last[0]))  # jdoe, johnd, jd


BAD_NAME = re.compile(r"^(\*|disclaimer|total|grand total|name|investor name|n/?a$)", re.I)


# ---------------------------------------------------------------------------
# Where each file came from (so every record can be traced back)
# ---------------------------------------------------------------------------
def airtable_sources():
    """{share-link path: source name} for the Airtable links in the Notion export."""
    ws = openpyxl.load_workbook(NOTION_EXPORT, read_only=True).active
    found = {}
    for row in ws.iter_rows(values_only=True):
        for cell in row[1:3]:
            m = re.search(r"airtable\.com/(\S+)", str(cell or ""))
            if m:
                found.setdefault(m.group(1).split("?")[0], (row[0], "https://airtable.com/" + m.group(1)))
    return found


AIRTABLE_CSV_NAMES = {"USA seed VCs-Grid view.csv": "USA Angel investors (Meet.Capital) - USA seed VCs",
                      "Early Stage NYC VCs-Grid view.csv": "NYC Early Stage VC Firms"}


def match_airtable(ocr_url, known):
    """OCR may misread a few letters of the link; pick the closest known link."""
    path = re.sub(r"^https?://airtable\.com/", "", ocr_url or "")
    best = difflib.get_close_matches(path, list(known), n=1, cutoff=0.6)
    return known[best[0]] if best else ("Airtable (unknown)", ocr_url)


# ---------------------------------------------------------------------------
# One raw row -> one standard record
# ---------------------------------------------------------------------------
def to_record(values: dict, source_name, source_url, source_file):
    """values = {role: raw text}. Returns a clean record dict, or None if unusable."""
    g = lambda role: clean_text(values.get(role, ""))

    person = clean_name(g("person_name") or f"{g('first_name')} {g('last_name')}".strip())
    firm = clean_name(g("firm_name"))
    firm_type = clean_firm_type(g("firm_type"))
    # Some sources put an EMAIL in the company column: move it where it belongs.
    if "@" in firm:
        values = {**values, "contact_email": values.get("contact_email") or firm}
        firm = ""
    # A name needs at least 2 letters ('212', '$200' are misaligned cells).
    if len(re.findall(r"[^\W\d_]", firm)) < 2:
        firm = ""
    if len(re.findall(r"[^\W\d_]", person)) < 2 or "@" in person:
        person = ""
    # 'Jane Doe Partner at X' -> name 'Jane Doe', headline goes to the title.
    person, headline = split_name_headline(person)
    if headline:
        values = {**values, "title": headline}
    is_individual = ""
    if not firm and person:                 # individual investor (e.g. angel lists)
        firm = person
        firm_type = firm_type or "Angel"
        is_individual = "1"
    if not firm or len(firm) < 2 or BAD_NAME.match(firm):
        return None

    contact_email = clean_email(g("contact_email"))
    firm_email = clean_email(g("firm_email"))
    own_site = clean_website(g("website"))
    # Shifted rows can give a person someone else's email: keep it only if it fits.
    if contact_email and person and not email_fits_person(contact_email, person, own_site):
        contact_email = ""
    website = own_site or email_domain(firm_email) or email_domain(contact_email)
    location = g("location")
    address = location if re.search(r"\d", location) else ""   # has a street number -> address
    tmin, tmax = money_range(g("ticket"))
    # Separate "Min ticket" / "Max ticket" columns beat a combined range.
    if g("ticket_min"):
        tmin = money_range(g("ticket_min"))[0]
        tmax = money_range(g("ticket_max"))[1] if g("ticket_max") else ("" if not g("ticket") else tmax)
    elif g("ticket_max"):
        tmax = money_range(g("ticket_max"))[1]
    aum = clean_money(g("aum"))
    if aum and int(aum) < 1_000_000:        # AUM under $1M isn't plausible -> unit was lost
        aum = ""
    return {
        "source_name": source_name, "source_url": source_url, "source_file": source_file,
        "firm_name": firm, "firm_type": firm_type, "website": website,
        "country": clean_country(g("country")) or country_from_text(location) or country_from_text(g("state")),
        "city": clean_name(g("city")) or city_from_text(location),
        "address": address,
        "aum_usd": aum,
        "sectors": g("sectors")[:300], "stages": g("stages")[:200],
        "ticket_min_usd": tmin, "ticket_max_usd": tmax,
        "firm_linkedin": clean_linkedin(g("firm_linkedin")),
        "firm_email": firm_email,
        "firm_phone": clean_phone(g("firm_phone")),
        "description": g("description")[:1000],
        "legal_id": g("legal_id"),
        "is_individual": is_individual,     # "1" = the 'firm' is really one person
        "is_enrichment": "",
        "person_name": person,
        "title": g("title")[:150],
        "contact_email": contact_email,
        "contact_phone": clean_phone(g("contact_phone")),
        "contact_linkedin": clean_linkedin(g("contact_linkedin")),
    }


def records_from_file(path, source_name, source_url, is_ocr=False):
    header, rows = read_table(path)
    roles = map_columns(header)
    if is_ocr and not ({"firm_name", "person_name", "first_name"} & set(roles.values())):
        roles[0] = "firm_name"                # OCR misread the name header; column 1 is the name
    if not ({"firm_name", "person_name", "first_name"} & set(roles.values())):
        return [], len(rows), "SKIP: no name column"
    # Money columns may state their unit in the HEADER: "AUM (USD MN)", "Ticket ($k)".
    units = {i: header_unit(header[i]) for i, r in roles.items() if r in MONEY_ROLES}
    out = []
    for row in rows:
        values = {}
        for i, role in roles.items():
            if i < len(row) and row[i].strip():
                values[role] = row[i] + units.get(i, "")   # '2,134' + ' million'
        rec = to_record(values, source_name, source_url, os.path.basename(path))
        if rec:
            out.append(rec)
    return out, len(rows), "used"


# ---------------------------------------------------------------------------
# SEC Form D (already structured, so no column guessing needed)
# ---------------------------------------------------------------------------
def sec_records():
    funds_path, people_path = Path("data/raw/sec/form_d_funds.csv"), Path("data/raw/sec/form_d_people.csv")
    if not funds_path.exists():
        return []
    funds = pd.read_csv(funds_path, dtype=str).fillna("")
    # A fund files Form D many times (amendments): keep its LATEST filing.
    funds = funds.sort_values("accession").drop_duplicates("cik", keep="last")
    people = pd.read_csv(people_path, dtype=str).fillna("") if people_path.exists() else pd.DataFrame()
    out = []
    for f in funds.itertuples():
        base = {"firm_name": f.fund_name, "firm_type": f.fund_type,
                "location": f"{f.street}, {f.city}, {f.state_or_country}",
                "city": f.city.title(), "country": f.state_or_country,
                "firm_phone": f.phone, "legal_id": f"SEC CIK {f.cik}"}
        rec = to_record(base, "USA - SEC EDGAR (Form D API)", f.filing_url, "form_d_funds.csv")
        if rec:
            rec["address"] = f"{f.street}, {f.city.title()}, {f.state_or_country.title()} {f.zip}".strip(", ")
            out.append(rec)
    if len(people):
        keep = set(funds.accession)
        ppl = people[(people.accession.isin(keep)) & (people.is_company.str.lower() != "true")]
        names = funds.set_index("accession")
        for p in ppl.itertuples():
            f = names.loc[p.accession]
            rec = to_record({"firm_name": f.fund_name, "firm_type": f.fund_type, "person_name": p.full_name,
                             "title": p.roles, "country": f.state_or_country, "city": f.city.title()},
                            "USA - SEC EDGAR (Form D API)", f.filing_url, "form_d_people.csv")
            if rec:
                rec["legal_id"] = f"SEC CIK {f.cik}"
                out.append(rec)
    return out


# ---------------------------------------------------------------------------
# Blacklists: kept apart - they flag investors, they don't add them
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# SEC Form ADV (enrichment only): AUM, website, phone, address of US advisers
# ---------------------------------------------------------------------------
def adv_records():
    out = []
    for kind, aum_col in (("registered", "5F(2)(c)"), ("exempt", "Total Gross Assets of Private Funds")):
        path = Path(f"data/raw/sec_adv/{kind}.csv")
        if not path.exists():
            continue
        df = pd.read_csv(path, dtype=str, encoding="latin-1").fillna("")
        for values in df.itertuples(index=False, name=None):
            row = dict(zip(df.columns, values))      # {column name: value} for this adviser
            site = row["Website Address"]
            base = {
                "website": site,
                "firm_linkedin": site if "linkedin.com" in site.lower() else "",
                "location": f"{row['Main Office City']}, {row['Main Office State']}, {row['Main Office Country']}",
                "city": row["Main Office City"].title(),
                "country": row["Main Office Country"],
                "firm_phone": row["Main Office Telephone Number"],
                "aum": row[aum_col],
            }
            address = ", ".join(x.title() for x in (row["Main Office Street Address 1"], row["Main Office Street Address 2"],
                                                     row["Main Office City"]) if x)
            address += f", {row['Main Office State']} {row['Main Office Postal Code']}".rstrip(", ")
            url = f"https://adviserinfo.sec.gov/firm/summary/{row['Organization CRD#']}"
            # One record per name the adviser goes by, so name matching has two chances.
            names = {row["Primary Business Name"], row["Legal Name"]} - {""}
            for name in names:
                rec = to_record({**base, "firm_name": name}, "SEC Form ADV (enrichment)", url, f"adv_{kind}.csv")
                if rec:
                    rec.update(address=address, legal_id=f"SEC CRD {row['Organization CRD#']}", is_enrichment="1")
                    out.append(rec)
    return out


def blacklist_rows(path, sheet_title, source_url):
    header, rows = read_table(path)
    norm = [h.lower().strip() for h in header]
    name_i = next((i for i, h in enumerate(norm) if h in ("investor name", "name", "investor", "company name")), 0)
    type_i = next((i for i, h in enumerate(norm) if "type" in h), None)
    why_i = next((i for i, h in enumerate(norm) if h.startswith("ration") or "reason" in h or "status" in h), None)
    client = re.sub(r"\s*black\s*list.*$", "", sheet_title, flags=re.I).strip() or sheet_title
    out = []
    for r in rows:
        raw = r[name_i] if name_i < len(r) else ""
        name = clean_name(re.split(r"\s+/\s+|\s+-\s+HNWI", raw)[0])   # 'Ofir Naor / HNWI' -> 'Ofir Naor'
        if name and not BAD_NAME.match(name):
            out.append({"firm_name": name, "website": "", "client": client,
                        "investor_type": clean_text(r[type_i]) if type_i is not None and type_i < len(r) else "",
                        "reason": clean_text(r[why_i]) if why_i is not None and why_i < len(r) else "",
                        "source_name": sheet_title, "source_url": source_url})
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = pd.read_csv("data/raw/gsheets/manifest.csv").fillna("")
    by_file = manifest.set_index("file")
    records, blacklist, report = [], [], []

    # 1) Google Sheets tabs
    for path in sorted(glob.glob("data/raw/gsheets/files/*.csv")):
        name = os.path.basename(path)
        info = by_file.loc[name] if name in by_file.index else None
        src_name = (info.source_names.split(" ; ")[0] if info is not None else name)
        src_url = info.url if info is not None else ""
        if info is not None and "Blacklist" in info.source_type:
            rows = blacklist_rows(path, info.sheet_title, src_url)
            blacklist += rows
            report.append((name, "blacklist", len(rows), len(rows)))
            continue
        reason = skip_reason(name)
        if reason:
            report.append((name, "SKIP: " + reason, 0, 0))
            continue
        recs, n_in, status = records_from_file(path, f"{src_name} [{info.tab if info is not None else ''}]", src_url)
        records += recs
        report.append((name, status, n_in, len(recs)))

    # 2) Airtable (OCR'd PDFs + CSV downloads)
    known = airtable_sources()
    for path in sorted(glob.glob("data/raw/airtable/ocr/*.csv")):
        name = os.path.basename(path)
        reason = skip_reason(name, is_ocr=True)
        if reason:
            report.append((f"airtable/{name}", "SKIP: " + reason, 0, 0))
            continue
        first_url = next((r["source_url"] for r in csv.DictReader(open(path, encoding="utf-8")) if r.get("source_url")), "")
        src_name, src_url = match_airtable(first_url, known)
        recs, n_in, status = records_from_file(path, f"{src_name} (Airtable)", src_url, is_ocr=True)
        records += recs
        report.append((f"airtable/{name}", status, n_in, len(recs)))
    for path in sorted(glob.glob("data/raw/airtable/*.csv")):
        name = os.path.basename(path)
        recs, n_in, status = records_from_file(path, AIRTABLE_CSV_NAMES.get(name, name) + " (Airtable)", "")
        records += recs
        report.append((f"airtable/{name}", status, n_in, len(recs)))

    # 3) SEC Form D
    sec = sec_records()
    records += sec
    report.append(("sec/form_d", "used" if sec else "SKIP: not downloaded yet", len(sec), len(sec)))

    # 4) SEC Form ADV - enrichment only (dedupe.py uses it just to fill gaps)
    adv = adv_records()
    records += adv
    report.append(("sec_adv", "enrichment" if adv else "SKIP: not downloaded yet", len(adv), len(adv)))

    pd.DataFrame(records, columns=RECORD_COLUMNS).to_csv(OUT / "staging_records.csv", index=False)
    pd.DataFrame(blacklist).to_csv(OUT / "blacklist_raw.csv", index=False)
    rep = pd.DataFrame(report, columns=["file", "status", "rows_in", "records_out"])
    rep.to_csv(OUT / "stage_report.csv", index=False)
    print(f"Staging records: {len(records):,}   Blacklist entries: {len(blacklist):,}")
    print(rep.status.str.extract(r"^(\w+)")[0].value_counts().to_string())


if __name__ == "__main__":
    main()
