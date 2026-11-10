"""
mapping.py - work out what each column in each raw file MEANS.

Every source names its columns differently ("Investor Name", "Firm", "Company
name"...). Here we give each column a ROLE - one of our standard fields - using
keyword rules. Files we shouldn't use (startup lists, fund/deal sub-tables...)
are skipped with a reason.

Main pieces:
  read_table(path)      -> (header, rows)  finds the real header row
  map_columns(header)   -> {column index: role}
  SKIP rules            -> which files to ignore and why
"""
import csv
import re

csv.field_size_limit(10**9)

# ----------------------------------------------------------------------------
# Files to skip (matched against the file name, lower-case). Reason is logged.
# ----------------------------------------------------------------------------
SKIP_FILE_PATTERNS = {
    "investment_entities": "portfolio startups, not investors",
    "investment_strateg": "sub-table of fund strategies (no firm names)",
    "investment_vehicles": "sub-table of individual funds",
    "__investments.csv": "sub-table of deals",
    "dealroom_people__people": "startup founders, not investors",
    "__cover.csv": "cover page", "__about.csv": "about page", "__info.csv": "info page",
    "readme": "notes page", "instructions": "notes page",
}
# OCR'd Airtable files that aren't usable investor lists (decided by inspection).
SKIP_OCR = {
    "10.csv": "Spanish startups list, not investors",
    "5.csv": "10 startup names (Female Angels list), not investors",
    "13.csv": "duplicate print of 12.csv",
    "19.csv": "card layout, OCR found no table",
    "11.csv": "OCR lost the name column",
}
# Layout/summary tabs (not lists).
SKIP_FILE_PATTERNS.update({"pivot_table": "summary pivot table", "filters_applied": "export notes",
                           "quick_stats": "summary stats", "browse_by_firm": "summary layout",
                           "top_businessman": "business families list, not investors"})


def skip_reason(file_name: str, is_ocr: bool = False) -> str:
    low = file_name.lower()
    if is_ocr and low in SKIP_OCR:
        return SKIP_OCR[low]
    for pattern, reason in SKIP_FILE_PATTERNS.items():
        if pattern in low:
            return reason
    return ""


# ----------------------------------------------------------------------------
# Reading a raw CSV and finding its real header row
# ----------------------------------------------------------------------------
def read_table(path):
    """Return (header, data_rows). The header is the row (in the first 10) with
    the most short, non-numeric labels - some sheets have titles above it."""
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return [], []

    def label_score(row):
        return sum(1 for c in row if c.strip() and len(c) < 70 and not re.fullmatch(r"[\d.,$%\s-]+", c))

    top = rows[:10]
    best = max(range(len(top)), key=lambda i: (label_score(top[i]), -i))
    if label_score(top[best]) <= 1:            # single-column list with no header
        return ["name"], [r[:1] for r in rows if r and r[0].strip()]
    header = [h.strip() for h in rows[best]]
    return header, rows[best + 1:]


# ----------------------------------------------------------------------------
# Column roles. Order matters: the FIRST matching column wins each role.
# Each rule: (role, exact header names, words that must appear, words that must NOT)
# ----------------------------------------------------------------------------
RULES = [
    ("first_name", {"first name", "contact first name", "firstname", "first"}, [], []),
    ("last_name", {"last name", "contact last name", "lastname", "surname", "last"}, [], []),
    ("person_name", {"full name", "contact full name", "person", "contact name", "contact 1 name",
                     "primary contact name", "key person / ceo", "contact", "name of contact",
                     "contact person", "decision maker", "partner name", "angel investor full name",
                     "best contact"}, [], []),
    ("firm_name", {"investor name", "company name", "company", "firm name", "firm", "family office name",
                   "entity name", "investor", "vc name", "vc", "fund name", "organization", "organisation",
                   "bank name", "family office", "company name for emails", "account name", "institution",
                   "lp name", "name of the fund", "organization name", "fund", "investor/firm",
                   "name of family office", "fund manager", "investors name", "firm/fund name",
                   "vc firms", "vc firm", "family office / entity", "vc funds", "company / investor",
                   "fund of fund name", "swf name", "organization/person name", "investor name:",
                   "fund", "organisation name"},
     ["investor name"], []),
    ("name", {"name"}, [], []),                         # decided later: firm or person
    ("title", {"title", "job title", "contact 1 title", "primary contact title", "position", "role",
               "designation", "contact title"}, [], ["role within"]),
    ("website", {"website", "url", "urls", "domain", "company domain", "favoriteurl", "web", "site",
                 "homepage", "website url", "company website", "web site", "firm website"}, ["website"],
     ["linkedin"]),
    ("email", {"email", "emails", "e-mail", "primary email", "favoriteemail", "email address", "contact email",
               "work email", "email 1", "contact 1 email", "mail"}, ["email"], ["risk", "secondary", "status"]),
    ("firm_linkedin", set(), ["linkedin"], ["person", "personal", "profile", "contact", "bio", "followers"]),
    ("contact_linkedin", set(), ["linkedin"], ["company", "firm", "bio", "followers"]),
    ("phone", set(), ["phone"], ["secondary"]),
    ("country", {"country", "hq country", "headquarters country", "bank country", "country of origin",
                 "country hq", "nation", "investor country"}, [], ["focus"]),
    ("city", {"city", "hq city", "bank city", "\x08city", "town"}, [], []),
    ("state", {"state", "bank state", "state/province", "province"}, [], []),
    ("location", {"location", "hq", "headquarters", "address", "addresses", "favoriteaddress",
                  "contact location", "hq location", "bank street address", "office", "based in"}, [], ["focus"]),
    ("firm_type", {"investor type", "type", "entity type", "category", "investor category",
                   "type of investor", "firm type", "organization type"}, ["investor type"], []),
    ("sectors", {"sector focus", "sectors", "industry", "industries", "preferred sectors", "verticals",
                 "focus areas", "sector", "focus", "sector/focus areas", "investment focus",
                 "sector focus (e.g. only saas, only fintech)", "keywords"}, ["sector"], ["region", "country", "geograph", "stage"]),
    ("stages", {"stage", "stage focus", "investment stage", "investment stage and ticket", "stages",
                "funding stage", "investment stages"}, ["stage"], ["lifecycle"]),
    ("aum", {"aum", "aum approx", "aum in usd", "aum range", "assets under management", "aum (usd)",
             "aum ($)"}, ["aum"], []),
    ("ticket_min", {"min ticket", "minimum ticket", "min check", "min check size", "minimum check size",
                    "minimum investment", "min investment", "min ticket size"}, [], []),
    ("ticket_max", {"max ticket", "maximum ticket", "max check", "max check size", "maximum check size",
                    "maximum investment", "max investment", "max ticket size"}, [], []),
    ("ticket", {"check size", "ticket size", "deal size range", "investment size", "ticket",
                "typical check size", "cheque size"}, ["check size", "ticket"], ["stage"]),
    ("description", {"description", "desc", "about", "investment thesis", "blurb", "headline",
                     "bank description / investing thesis", "overview", "summary", "bio", "notes"},
     ["description", "thesis"], []),
]


def _norm(h: str) -> str:
    """Lower-case, no invisible characters, underscores -> spaces."""
    h = h.replace("\x08", "").replace("﻿", "").replace("_", " ")
    return re.sub(r"\s+", " ", h.strip().lower())


def map_columns(header):
    """Return {column index: role} for one file's header."""
    roles = {}
    taken = set()
    normed = [_norm(h) for h in header]
    # "investor name" next to a company column is a PERSON (e.g. Fundraisr lists).
    person_investor = "investor name" in normed and ({"company name", "company"} & set(normed))
    for i, raw in enumerate(header):
        h = normed[i]
        if not h:
            continue
        if person_investor and h == "investor name":
            roles[i] = "person_name"
            taken.add("person_name")
            continue
        for role, exact, must, must_not in RULES:
            if role in taken and role not in ("description",):
                continue
            hit = h in exact or (must and any(m in h for m in must))
            if hit and not any(x in h for x in must_not):
                if role == "description" and "description" in taken:
                    break                         # keep only the first description
                roles[i] = role
                taken.add(role)
                break

    has_person = {"first_name", "last_name", "person_name"} & taken
    has_firm = "firm_name" in taken
    # Resolve the ambiguous plain "Name" column.
    for i, role in list(roles.items()):
        if role == "name":
            roles[i] = "person_name" if (has_person - {"person_name"} or has_firm) and "person_name" not in taken \
                else "firm_name" if not has_firm else None
            if roles[i] is None:
                del roles[i]
    taken = set(roles.values())
    has_person = bool({"first_name", "last_name", "person_name"} & taken)
    # Email: a person's email if the file is about people, else the firm's.
    for i, role in list(roles.items()):
        if role == "email":
            roles[i] = "contact_email" if has_person else "firm_email"
        if role == "phone":
            roles[i] = "contact_phone" if has_person else "firm_phone"
    # A LinkedIn column that could be either: decide by whether there are people.
    lk = [i for i, r in roles.items() if r in ("firm_linkedin", "contact_linkedin")]
    if len(lk) == 1:
        h = _norm(header[lk[0]])
        if not any(w in h for w in ("company", "firm", "person", "personal", "profile", "contact")):
            roles[lk[0]] = "contact_linkedin" if has_person else "firm_linkedin"
    return roles
