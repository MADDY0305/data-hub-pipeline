"""
websites.py - EXTRACT facts from each firm's OWN public homepage (enrichment).

For every firm that has a website but is missing a description, LinkedIn,
email or phone, we read its homepage (and, if needed, its contact page) and
pull out:
  - description : the site's own summary (<meta name="description">)
  - linkedin    : a link to linkedin.com/company/...
  - email       : addresses on the firm's own domain (info@, contact@ first)
  - phone       : "tel:" links

POLITE BY DESIGN (see CLAUDE.md rule 2):
  - robots.txt is checked first; if the site says "don't", we skip it.
  - Max 2 pages per site, at least 3 seconds apart.
  - Many DIFFERENT sites are read in parallel, so the whole run is still fast.
  - We say who we are (User-Agent) and only save the extracted facts.

Output: data/raw/websites/results.csv  (one row per domain; safe to stop and re-run)
Run:    .venv/Scripts/python -m extract.websites            (all)
        .venv/Scripts/python -m extract.websites 40         (test on 40 sites)
"""
import csv
import re
import socket
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import pandas as pd
import requests
from bs4 import BeautifulSoup

OUT = Path("data/raw/websites/results.csv")
AGENT = "DataHubPipeline/1.0 (+https://github.com/MADDY0305/data-hub-pipeline)"
HEADERS = {"User-Agent": AGENT, "Accept": "text/html", "Accept-Language": "en"}
PER_SITE_PAUSE = 3          # seconds between two requests to the SAME site
WORKERS = 48                # different sites read at the same time (each site still sees the slow pace)
MAX_BYTES = 2_000_000       # ignore pages bigger than 2 MB
PAGE_DEADLINE = 25          # give up on one page after 25 seconds of downloading
SITE_DEADLINE = 120         # a whole site (robots + up to 3 pages + pauses) gets 2 minutes max
socket.setdefaulttimeout(20)  # safety net for any network call without its own timeout
FIELDS = ["domain", "status", "final_url", "description", "linkedin", "email", "phone", "fetched_at"]
GENERIC_BOXES = ("info", "contact", "hello", "office", "enquiries", "inquiries", "ir", "invest",
                 "admin", "team", "general", "mail")
# Mailboxes that aren't for investor contact (jobs, press, privacy, robots...).
SKIP_BOXES = re.compile(r"^(no-?reply|do-?not-?reply|careers?|jobs?|recrut|recruit|hr|talent|press|media|"
                        r"privacy|gdpr|dpo|datenschutz|webmaster|postmaster|abuse|support|billing|"
                        r"accounts?|newsletter|unsubscribe|example|your|name|email)", re.I)
BAD_DESC = re.compile(r"cookie|javascript|enable js|just a moment|access denied|coming soon|"
                      r"under construction|page not found|404|domain (is )?for sale", re.I)


def read_body(r, max_bytes):
    """Read a response in small pieces, giving up after PAGE_DEADLINE seconds.
    (requests' own timeout only covers silence between bytes - a site that
    drips one byte every few seconds could otherwise keep us forever.)"""
    start, chunks, size = time.monotonic(), [], 0
    for chunk in r.iter_content(16_384):
        chunks.append(chunk)
        size += len(chunk)
        if size > max_bytes:
            return None, "too_big"
        if time.monotonic() - start > PAGE_DEADLINE:
            return None, "too_slow"
    return b"".join(chunks), ""


def fetch(url):
    """Download one page (HTML only, size-limited). Returns (final_url, html) or (None, reason)."""
    try:
        with requests.get(url, headers=HEADERS, timeout=(10, 15), stream=True, allow_redirects=True) as r:
            if r.status_code != 200:
                return None, f"http_{r.status_code}"
            if "html" not in r.headers.get("Content-Type", ""):
                return None, "not_html"
            body, why = read_body(r, MAX_BYTES)
            if body is None:
                return None, why
            return r.url, body.decode(r.encoding or "utf-8", errors="replace")
    except Exception as e:                       # any network/decoding problem = skip this page
        return None, type(e).__name__


def allowed(domain):
    """Does the site's robots.txt allow us to read its homepage?"""
    rp = RobotFileParser()
    try:
        with requests.get(f"https://{domain}/robots.txt", headers=HEADERS, timeout=(10, 10), stream=True) as r:
            if r.status_code >= 400:
                return True                      # no robots.txt = no restrictions
            body, _ = read_body(r, 500_000)
            if body is None:
                return True
            rp.parse(body.decode("utf-8", errors="replace").splitlines())
            return rp.can_fetch(AGENT, f"https://{domain}/")
    except Exception:
        return True                              # unreachable robots.txt: homepage fetch will tell


def extract(html, base_url, domain):
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    # Description: the site's own summary.
    for attrs in ({"name": "description"}, {"property": "og:description"}, {"name": "twitter:description"}):
        tag = soup.find("meta", attrs=attrs)
        text = re.sub(r"\s+", " ", (tag.get("content") or "")).strip() if tag else ""
        if len(text) >= 40 and not BAD_DESC.search(text):
            out["description"] = text[:1000]
            break
    links = [a.get("href", "") for a in soup.find_all("a", href=True)]
    # LinkedIn company page.
    lk = next((h for h in links if re.search(r"linkedin\.com/(company|school)/", h, re.I)), "")
    if lk:
        m = re.search(r"linkedin\.com/(company|school)/[^/?#\s\"']+", lk, re.I)
        out["linkedin"] = "https://www." + m.group(0).lower() if m else ""
    # Emails on the firm's OWN domain only (generic mailboxes first).
    found = {h[7:].split("?")[0].strip().lower() for h in links if h.lower().startswith("mailto:")}
    found |= set(re.findall(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", soup.get_text(" ").lower()))
    own = sorted(e for e in found if (e.endswith("@" + domain) or e.endswith("." + domain))
                 and not SKIP_BOXES.search(e.split("@")[0]))
    if own:
        out["email"] = sorted(own, key=lambda e: (e.split("@")[0] not in GENERIC_BOXES, len(e)))[0]
    # Phone from tel: links.
    tel = next((h[4:].strip() for h in links if h.lower().startswith("tel:")), "")
    if len(re.sub(r"\D", "", tel)) >= 7:
        out["phone"] = re.sub(r"[^\d+() .-]", "", tel).strip()
    # A contact page link, in case we still need email/phone.
    contact = next((urljoin(base_url, h) for h in links
                    if re.search(r"contact|kontakt|contacto|impressum|imprint", h, re.I)
                    and urlparse(urljoin(base_url, h)).netloc.endswith(domain)), "")
    return out, contact


def visit(domain):
    row = {f: "" for f in FIELDS}
    row.update(domain=domain, fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    if not allowed(domain):
        row["status"] = "robots_disallow"
        return row
    time.sleep(PER_SITE_PAUSE)
    final, html = fetch(f"https://{domain}/")
    if final is None:                             # try plain http + www as a fallback
        time.sleep(PER_SITE_PAUSE)
        final, html = fetch(f"http://www.{domain}/")
    if final is None:
        row["status"] = html
        return row
    data, contact = extract(html, final, domain)
    if contact and not (data.get("email") and data.get("phone")):
        time.sleep(PER_SITE_PAUSE)
        c_final, c_html = fetch(contact)
        if c_final:
            extra, _ = extract(c_html, c_final, domain)
            for k, v in extra.items():
                data.setdefault(k, v)
    row.update(status="ok", final_url=final, **data)
    return row


def main(limit=None):
    inv = pd.read_csv("data/clean/investors.csv", dtype=str).fillna("")
    need = inv[(inv.website != "") & ((inv.description == "") | (inv.firm_linkedin == "")
                                      | (inv.firm_email == "") | (inv.firm_phone == ""))]
    domains = list(dict.fromkeys(need.website))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    done = set(pd.read_csv(OUT, dtype=str).domain) if OUT.exists() else set()
    todo = [d for d in domains if d not in done][:limit]
    print(f"{len(domains):,} domains need data; {len(done):,} already done; visiting {len(todo):,} now", flush=True)

    # WATCHDOG: we keep WORKERS sites "in flight". If one site takes longer than
    # SITE_DEADLINE (e.g. its name lookup never answers), we write it down as
    # "timeout" and start another site in its place. Python can't kill a stuck
    # thread, so the pool has spare threads; when too many are stuck we open a
    # fresh pool. Last time 48 stuck sites silently froze the whole run.
    new_file = not OUT.exists()
    queue, n = list(reversed(todo)), 0
    with open(OUT, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        pool, stuck_here = ThreadPoolExecutor(WORKERS * 4), 0
        running = {}                                  # future -> (domain, start time)
        while queue or running:
            while queue and len(running) < WORKERS:
                d = queue.pop()
                running[pool.submit(visit, d)] = (d, time.monotonic())
            done, _ = wait(running, timeout=5, return_when=FIRST_COMPLETED)
            finished = []
            for fut in done:
                d, _ = running.pop(fut)
                try:
                    finished.append(fut.result())
                except Exception as e:                # a bug on one odd page shouldn't stop the run
                    finished.append({**{k: "" for k in FIELDS}, "domain": d, "status": type(e).__name__})
            now = time.monotonic()
            for fut, (d, t0) in list(running.items()):
                if now - t0 > SITE_DEADLINE:          # give up on it, move on
                    running.pop(fut)
                    stuck_here += 1
                    finished.append({**{k: "" for k in FIELDS}, "domain": d, "status": "timeout",
                                     "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
            for row in finished:
                w.writerow(row)
                n += 1
                if n % 500 == 0 or n == len(todo):
                    print(f"  {n:,}/{len(todo):,} sites visited", flush=True)
            f.flush()                                 # save progress every loop
            if stuck_here >= WORKERS * 2:             # too many frozen threads: fresh pool
                pool.shutdown(wait=False)
                pool, stuck_here = ThreadPoolExecutor(WORKERS * 4), 0
        pool.shutdown(wait=False)
    print(f"Done: {n:,} sites written to {OUT}", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
