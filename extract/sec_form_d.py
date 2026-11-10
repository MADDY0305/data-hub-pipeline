"""
sec_form_d.py - EXTRACT step using a real API: SEC EDGAR (free, no key).

WHAT IS FORM D?
  When a US fund (VC, private equity, hedge...) raises money privately it must
  file "Form D" with the SEC. Each filing lists the fund's name, address, phone,
  fund type, how much it raised, and the people behind it (GPs, directors).

HOW THIS SCRIPT WORKS (two APIs):
  1. SEARCH API  efts.sec.gov/LATEST/search-index
     -> "give me every Form D mentioning 'Venture Capital Fund' filed in March"
     Returns 100 results per page; we page through them. One search can return
     at most 10,000 results, so we search one MONTH at a time.
  2. ARCHIVE     www.sec.gov/Archives/edgar/data/<cik>/<accession>/primary_doc.xml
     -> the filing itself, as XML (structured text with <tags>).
     We save the XML untouched (raw layer), then pull out the fields we need.

SEC RULES WE FOLLOW:
  - Every request says who we are (User-Agent header from .env).
  - Max 10 requests per second - we do about 8.

Output:
  data/raw/sec/xml/<accession>.xml   untouched filings (raw layer)
  data/raw/sec/form_d_funds.csv      one row per fund filing
  data/raw/sec/form_d_people.csv     one row per person/company named in a filing

Run:  .venv/Scripts/python -m extract.sec_form_d 2026-01-01 2026-10-31
Safe to re-run: filings already downloaded are not fetched again.
"""
import csv
import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
HEADERS = {"User-Agent": os.environ["SEC_USER_AGENT"]}
SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/primary_doc.xml"
OUT = Path("data/raw/sec")
XML_DIR = OUT / "xml"
# Phrases that appear in the "fund type" box of Form D.
SEARCH_PHRASES = ['"Venture Capital Fund"', '"Private Equity Fund"']
PAUSE = 0.2  # 5 requests/second (SEC limit is 10 - we stay well under)
COMPANY_WORDS = (" llc", " l.l.c", " lp", " l.p.", " ltd", " inc", " gp", " partners", " capital",
                 " management", " s.a r.l", " sarl", " limited", " fund", " corp", " holdings")


SESSION = requests.Session()      # one reused connection = friendlier to the SEC
SESSION.headers.update(HEADERS)


def get(url, **params):
    """GET with a polite pause; if the SEC is busy or the connection drops,
    wait (longer each time) and try again instead of giving up."""
    for attempt in range(6):
        time.sleep(PAUSE)
        try:
            r = SESSION.get(url, params=params or None, timeout=30)
        except (requests.ConnectionError, requests.Timeout):
            time.sleep(10 * (attempt + 1))          # 10s, 20s, 30s...
            continue
        if r.status_code == 200:
            return r
        if r.status_code in (403, 429, 500, 502, 503):   # busy / slow down
            time.sleep(10 * (attempt + 1))
            continue
        r.raise_for_status()
    raise RuntimeError(f"SEC kept refusing: {url}")


def months(start: date, end: date):
    """Split a date range into whole months: [(2026-01-01, 2026-01-31), ...]."""
    d = start
    while d <= end:
        nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        yield d, min(nxt - timedelta(days=1), end)
        d = nxt


def search_filings(start: date, end: date):
    """Yield (accession number, cik) for every matching Form D in the range."""
    seen = set()
    for phrase in SEARCH_PHRASES:
        for m_start, m_end in months(start, end):
            offset, total = 0, None
            while total is None or offset < min(total, 10_000):
                # forms="D" returns originals AND amendments (D/A)
                j = get(SEARCH_URL, q=phrase, forms="D", dateRange="custom",
                        startdt=m_start.isoformat(), enddt=m_end.isoformat(), **{"from": offset}).json()
                total = j["hits"]["total"]["value"]
                hits = j["hits"]["hits"]
                if not hits:
                    break
                for h in hits:
                    acc = h["_source"]["adsh"]
                    if acc not in seen:
                        seen.add(acc)
                        yield acc, h["_source"]["ciks"][0]
                offset += len(hits)
            print(f"  searched {phrase} {m_start:%Y-%m}: {total} hits (unique so far: {len(seen)})", flush=True)


def download(acc: str, cik: str) -> Path:
    """Save the filing XML (skip if we already have it)."""
    path = XML_DIR / f"{acc}.xml"
    if not path.exists():
        url = DOC_URL.format(cik=int(cik), acc=acc.replace("-", ""))
        path.write_bytes(get(url).content)
    return path


def text(node, path, default=""):
    """Read the text at a tag path inside the XML, or '' if it's missing."""
    found = node.find(path) if node is not None else None
    return (found.text or "").strip() if found is not None and found.text else default


def parse(path: Path):
    """Turn one Form D XML into (fund dict, list of people dicts)."""
    root = ET.parse(path).getroot()
    iss = root.find("primaryIssuer")
    off = root.find("offeringData")
    acc = path.stem
    fund = {
        "accession": acc,
        "form": text(root, "submissionType"),
        "cik": text(iss, "cik"),
        "fund_name": text(iss, "entityName"),
        "entity_type": text(iss, "entityType"),
        "street": text(iss, "issuerAddress/street1"),
        "city": text(iss, "issuerAddress/city"),
        "state_or_country": text(iss, "issuerAddress/stateOrCountryDescription"),
        "zip": text(iss, "issuerAddress/zipCode"),
        "phone": text(iss, "issuerPhoneNumber"),
        "jurisdiction": text(iss, "jurisdictionOfInc"),
        "year_of_inc": text(iss, "yearOfInc/value"),
        "industry_group": text(off, "industryGroup/industryGroupType"),
        "fund_type": text(off, "industryGroup/investmentFundInfo/investmentFundType"),
        "first_sale_date": text(off, "typeOfFiling/dateOfFirstSale/value"),
        "min_investment_usd": text(off, "minimumInvestmentAccepted"),
        "total_offering_usd": text(off, "offeringSalesAmounts/totalOfferingAmount"),
        "total_sold_usd": text(off, "offeringSalesAmounts/totalAmountSold"),
        "num_investors": text(off, "investors/totalNumberAlreadyInvested"),
        "filing_url": f"https://www.sec.gov/Archives/edgar/data/{int(text(iss, 'cik') or 0)}/{acc.replace('-', '')}/",
    }
    people = []
    for p in root.findall("relatedPersonsList/relatedPersonInfo"):
        # Name parts; filers write "N/A" or "-" for empty parts, so drop those.
        parts = [text(p, f"relatedPersonName/{k}") for k in ("firstName", "middleName", "lastName")]
        full_name = " ".join(x for x in parts if x and x.upper() not in ("N/A", "NA", "-", "NONE"))
        is_company = any(w in f" {full_name.lower()}" for w in COMPANY_WORDS)
        people.append({
            "accession": acc,
            "cik": fund["cik"],
            "fund_name": fund["fund_name"],
            "full_name": full_name,
            "is_company": is_company,
            "roles": ", ".join(r.text for r in p.findall("relatedPersonRelationshipList/relationship") if r.text),
            "role_detail": text(p, "relationshipClarification"),
            "city": text(p, "relatedPersonAddress/city"),
            "state_or_country": text(p, "relatedPersonAddress/stateOrCountryDescription"),
        })
    return fund, people


def write_csv(path, rows):
    if rows:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)


def main(start: date, end: date):
    XML_DIR.mkdir(parents=True, exist_ok=True)
    print(f"1) Searching Form D filings {start} -> {end} ...")
    found = list(search_filings(start, end))
    print(f"   {len(found)} unique filings found.\n2) Downloading filings (about 5 per second) ...")
    for i, (acc, cik) in enumerate(found, 1):
        try:
            download(acc, cik)
        except Exception as e:
            print(f"   skip {acc}: {type(e).__name__}")
        if i % 500 == 0:
            print(f"   {i}/{len(found)} downloaded", flush=True)

    print("3) Reading the XML files ...")
    funds, people = [], []
    for path in sorted(XML_DIR.glob("*.xml")):
        try:
            f, p = parse(path)
        except ET.ParseError:
            continue
        # Keep only real investment funds of the types we want.
        if f["fund_type"] in ("Venture Capital Fund", "Private Equity Fund"):
            funds.append(f)
            people += p
    write_csv(OUT / "form_d_funds.csv", funds)
    write_csv(OUT / "form_d_people.csv", people)
    print(f"Done: {len(funds)} VC/PE fund filings, {len(people)} people/companies -> {OUT}")


if __name__ == "__main__":
    s = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date(date.today().year, 1, 1)
    e = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date.today()
    main(s, e)
