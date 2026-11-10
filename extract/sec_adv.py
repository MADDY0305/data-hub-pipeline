"""
sec_adv.py - EXTRACT the SEC investment-adviser list (Form ADV), free bulk download.

Every US investment adviser - including most VC and PE managers - files Form ADV.
The SEC publishes the whole list every month as two zipped CSV files:
  - "registered" advisers: bigger firms; includes regulatory AUM (field 5F(2)(c))
  - "exempt reporting" advisers: mostly VC / private-fund managers; includes
    "Total Gross Assets of Private Funds"
Both include website, phone and main-office address.

We use this for ENRICHMENT only (filling gaps in firms we already have), never
to add new investors - most advisers are wealth managers we don't target.

Output:  data/raw/sec_adv/registered.csv and exempt.csv (untouched SEC data)
Run:     .venv/Scripts/python -m extract.sec_adv
"""
import io
import os
import re
import zipfile
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(".env")
HEADERS = {"User-Agent": os.environ["SEC_USER_AGENT"]}
PAGE = ("https://www.sec.gov/data-research/sec-markets-data/"
        "information-about-registered-investment-advisers-exempt-reporting-advisers")
OUT = Path("data/raw/sec_adv")


def file_date(link: str) -> str:
    """'ia110226-registered.zip' / 'ia11022026-exempt.zip' -> '2026-11-02' (sortable)."""
    digits = re.search(r"/ia(\d{6,8})", link).group(1)
    mm, dd, yy = digits[:2], digits[2:4], digits[4:]
    return f"{'20' + yy if len(yy) == 2 else yy}-{mm}-{dd}"


def latest_links():
    """Find the newest 'registered' and 'exempt' zip links on the SEC page."""
    html = requests.get(PAGE, headers=HEADERS, timeout=60).text
    links = set(re.findall(r'href="(/files/investment/data/[^"]*/ia\d{6,8}[^"]*\.zip)"', html))
    # Look at the FILE name only - the folder name also contains "exempt".
    name = lambda l: l.rsplit("/", 1)[-1]
    exempt = sorted((l for l in links if "exempt" in name(l)), key=file_date)
    registered = sorted((l for l in links if "exempt" not in name(l)), key=file_date)
    return {"registered": registered[-1], "exempt": exempt[-1]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for kind, link in latest_links().items():
        r = requests.get("https://www.sec.gov" + link, headers=HEADERS, timeout=300)
        r.raise_for_status()
        z = zipfile.ZipFile(io.BytesIO(r.content))
        csv_name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        (OUT / f"{kind}.csv").write_bytes(z.read(csv_name))
        print(f"{kind:10} <- {link.rsplit('/', 1)[-1]}  ({len(r.content) / 1e6:.1f} MB zipped)")


if __name__ == "__main__":
    main()
