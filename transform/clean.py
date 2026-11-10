"""
clean.py - small functions that each fix ONE kind of messy value.

Every source writes things differently. These functions make the same thing
look the same everywhere, so we can compare and merge records:

    clean_website("HTTPS://www.Abc.com/about")  -> "abc.com"
    clean_country("USA")                        -> "United States"
    firm_key("Sequoia Capital, L.P.")           -> "sequoia capital"

Each returns "" when the value is empty or unusable, never crashes.
"""
import re
import unicodedata

import pycountry

# ---------- generic text ----------

JUNK = {"", "n/a", "na", "none", "null", "nan", "-", "--", "?", "tbd", "unknown", "#n/a", "0"}


def clean_text(value) -> str:
    """Trim spaces, fix odd characters, turn junk like 'N/A' into ''."""
    if value is None:
        return ""
    s = unicodedata.normalize("NFKC", str(value)).replace(" ", " ").replace("\x08", "")
    s = re.sub(r"\s+", " ", s).strip(" \t\n,;|")
    return "" if s.lower() in JUNK else s


# ---------- websites / domains ----------

# Sites that are NOT a firm's own website (can't identify a firm by them).
NOT_FIRM_DOMAINS = {
    "linkedin.com", "crunchbase.com", "twitter.com", "x.com", "facebook.com", "instagram.com",
    "angel.co", "wellfound.com", "airtable.com", "google.com", "docs.google.com", "bit.ly",
    "medium.com", "substack.com", "youtube.com", "pitchbook.com", "dealroom.co", "tracxn.com",
    "notion.so", "notion.site", "github.com", "wix.com", "wixsite.com", "sites.google.com",
    "linktr.ee", "about.me", "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
}
FREE_EMAIL = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com", "aol.com",
              "live.com", "msn.com", "proton.me", "protonmail.com", "me.com", "mail.com",
              "yahoo.co.uk", "googlemail.com", "gmx.de", "web.de", "qq.com", "163.com"}


def clean_website(value) -> str:
    """Reduce any web address to its bare domain: 'https://www.abc.com/x' -> 'abc.com'."""
    s = clean_text(value).lower()
    if not s or "..." in s or "…" in s:          # shortened by the source: unusable
        return ""
    s = s.split()[0].strip("<>\"'()[]")          # first token only
    s = re.sub(r"^[a-z]+:/*", "", s)             # drop http:// https:/ etc.
    s = s.split("/")[0].split("?")[0].split("#")[0].split(":")[0]
    s = re.sub(r"^(www\d?|m)\.", "", s)
    if "@" in s:                                 # an email slipped in
        s = s.split("@")[-1]
    if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", s):
        return ""
    if s in NOT_FIRM_DOMAINS or any(s.endswith("." + d) for d in NOT_FIRM_DOMAINS):
        return ""
    return s


def clean_email(value) -> str:
    """Lower-case and validate an email; '' if it doesn't look like one."""
    s = clean_text(value).lower().replace("mailto:", "")
    m = re.search(r"[a-z0-9._%+'-]+@[a-z0-9.-]+\.[a-z]{2,}", s)
    return m.group(0) if m else ""


# Personal-email providers in any country version (hotmail.co.uk, yahoo.fr, ...).
FREE_EMAIL_PREFIXES = ("gmail.", "googlemail.", "yahoo.", "ymail.", "hotmail.", "outlook.", "live.",
                       "msn.", "aol.", "icloud.", "gmx.", "web.", "mail.", "yandex.", "proton", "zoho.",
                       "rediffmail.", "naver.", "hanmail.", "free.", "orange.", "laposte.", "libero.",
                       "t-online.", "btinternet.", "bigpond.", "comcast.", "verizon.", "att.", "sbcglobal.",
                       "rogers.", "shaw.", "sky.", "virginmedia.", "wanadoo.", "seznam.", "wp.", "o2.")
FREE_EMAIL |= {"mac.com", "me.com", "qq.com", "163.com", "126.com", "sina.com", "foxmail.com", "fastmail.com",
               "hey.com", "tutanota.com", "mail.ru", "inbox.ru", "bk.ru", "list.ru", "rambler.ru"}


def email_domain(email: str) -> str:
    """Company domain from a work email (personal email providers don't count)."""
    d = email.split("@")[-1].lower() if "@" in email else ""
    if not d or d in FREE_EMAIL or d.startswith(FREE_EMAIL_PREFIXES):
        return ""
    return clean_website(d)


def clean_linkedin(value) -> str:
    """Keep only real LinkedIn links, in one standard form."""
    s = clean_text(value)
    m = re.search(r"linkedin\.com/(in|company|pub|school)/[^\s?#\"']+", s, re.I)
    return "https://www." + m.group(0).rstrip("/").lower() if m else ""


def clean_phone(value) -> str:
    """Keep digits, + and spaces; '' if fewer than 7 digits."""
    s = clean_text(value)
    s = re.split(r"[;,/]| or ", s)[0]            # first number if several
    s = re.sub(r"[^\d+() .-]", "", s).strip()
    return s if len(re.sub(r"\D", "", s)) >= 7 else ""


# ---------- countries ----------

ALIASES = {
    "usa": "United States", "us": "United States", "u.s.": "United States", "u.s.a.": "United States",
    "united states of america": "United States", "america": "United States",
    "uk": "United Kingdom", "u.k.": "United Kingdom", "england": "United Kingdom",
    "scotland": "United Kingdom", "wales": "United Kingdom", "great britain": "United Kingdom",
    "britain": "United Kingdom", "uae": "United Arab Emirates", "dubai": "United Arab Emirates",
    "abu dhabi": "United Arab Emirates", "ksa": "Saudi Arabia", "russia": "Russia",
    "south korea": "South Korea", "korea": "South Korea", "taiwan": "Taiwan", "vietnam": "Vietnam",
    "hong kong": "Hong Kong", "hk": "Hong Kong", "czech republic": "Czechia", "turkey": "Turkey",
    "holland": "Netherlands", "the netherlands": "Netherlands", "iran": "Iran", "syria": "Syria",
    "cayman islands": "Cayman Islands", "bvi": "British Virgin Islands", "macau": "Macao",
    "singapore": "Singapore", "luxemburg": "Luxembourg",
    # common native-language names
    "deutschland": "Germany", "espana": "Spain", "españa": "Spain", "schweiz": "Switzerland",
    "suisse": "Switzerland", "svizzera": "Switzerland", "italia": "Italy", "brasil": "Brazil",
    "méxico": "Mexico", "nederland": "Netherlands", "österreich": "Austria", "sverige": "Sweden",
    "danmark": "Denmark", "norge": "Norway", "suomi": "Finland", "polska": "Poland",
    "belgique": "Belgium", "belgië": "Belgium", "ksa (saudi arabia)": "Saudi Arabia",
}
US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut", "delaware",
    "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas", "kentucky",
    "louisiana", "maine", "maryland", "massachusetts", "michigan", "minnesota", "mississippi",
    "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey", "new mexico",
    "new york", "north carolina", "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania",
    "rhode island", "south carolina", "south dakota", "tennessee", "texas", "utah", "vermont",
    "virginia", "washington", "west virginia", "wisconsin", "wyoming", "district of columbia",
}
US_STATE_CODES = {"AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN",
                  "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV",
                  "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN",
                  "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC"}
# Short, friendly names instead of the official long ones.
FRIENDLY = {"Korea, Republic of": "South Korea", "Russian Federation": "Russia",
            "Iran, Islamic Republic of": "Iran", "Viet Nam": "Vietnam", "Türkiye": "Turkey",
            "Taiwan, Province of China": "Taiwan", "Syrian Arab Republic": "Syria",
            "Tanzania, United Republic of": "Tanzania", "Bolivia, Plurinational State of": "Bolivia",
            "Venezuela, Bolivarian Republic of": "Venezuela", "Moldova, Republic of": "Moldova",
            "Virgin Islands, British": "British Virgin Islands"}
_COUNTRY_NAMES = {}
for c in pycountry.countries:
    name = FRIENDLY.get(getattr(c, "common_name", c.name), getattr(c, "common_name", c.name))
    for n in {c.name, getattr(c, "common_name", c.name), getattr(c, "official_name", c.name)}:
        _COUNTRY_NAMES[n.lower()] = FRIENDLY.get(name, name)
    _COUNTRY_NAMES[c.alpha_3.lower()] = FRIENDLY.get(name, name)


def clean_country(value) -> str:
    """Turn any way of writing a country into one standard English name."""
    s = clean_text(value)
    if not s:
        return ""
    low = s.lower().strip(" .")
    if low in ALIASES:
        return ALIASES[low]
    if low in _COUNTRY_NAMES:
        return _COUNTRY_NAMES[low]
    if low in US_STATES or s.strip() in US_STATE_CODES:
        return "United States"
    return ""


def country_from_text(value) -> str:
    """Find a country inside free text like 'Menlo Park, CA' or 'London, UK'."""
    s = clean_text(value)
    if not s:
        return ""
    # Try each comma-separated piece from the END ('City, State, Country').
    for piece in reversed([p.strip() for p in re.split(r"[,/|;-]", s) if p.strip()]):
        found = clean_country(piece)
        if found:
            return found
    found = clean_country(s)
    if found:
        return found
    # No commas? Try the last 1-3 words ('Sacramento California', 'Rio de Janeiro Brazil').
    words = s.split()
    for n in (3, 2, 1):
        if len(words) > n:
            found = clean_country(" ".join(words[-n:]))
            if found:
                return found
    return ""


def city_from_text(value) -> str:
    """First part of 'City, State, Country' if it isn't itself a country."""
    s = clean_text(value)
    first = s.split(",")[0].strip() if s else ""
    return "" if not first or clean_country(first) else first.title() if first.isupper() else first


# ---------- names and matching keys ----------

LEGAL_ENDINGS = r"\b(l\.?l\.?c|l\.?l\.?p|l\.?p|ltd|limited|inc|incorporated|corp|corporation|co|company|" \
                r"gmbh|ag|sa|s\.a|sas|sarl|s\.a r\.l|bv|b\.v|nv|plc|pte|pty|ab|as|oy|kg|spa|srl|lda|scsp|fund i+|the)\b\.?"


def clean_name(value) -> str:
    """Tidy a firm or person name for display."""
    s = clean_text(value)
    s = re.sub(r"\s*\((cik|formerly)[^)]*\)", "", s, flags=re.I)
    s = s.strip(" .,-")
    if s.isupper() and len(s) > 4:               # 'SEQUOIA CAPITAL' -> 'Sequoia Capital'
        s = s.title()
        s = re.sub(r"\b(Llc|Lp|Llp|Ltd|Plc|Gp|Ag|Sa|Bv|Nv|Vc|Pe|Ii|Iii|Iv)\b",
                   lambda m: m.group(0).upper(), s)   # ...but keep 'LLC', 'LP', 'II' upper-case
    return s


def firm_key(name: str) -> str:
    """Matching key: lower-case, no punctuation, no legal endings.
    'Sequoia Capital, L.P.' and 'SEQUOIA CAPITAL LLC' both -> 'sequoia capital'."""
    s = unicodedata.normalize("NFKD", clean_text(name).lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))   # é -> e
    s = s.replace("&", " and ")
    s = re.sub(LEGAL_ENDINGS, " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) >= 2 else ""


HEADLINE_WORDS = re.compile(
    r"\s+(?=(investor|angel|partner|founder|co-founder|cofounder|ceo|cfo|cto|coo|cio|vice president|vp|"
    r"director|managing|principal|associate|chairman|chair|president|head|general partner|gp|"
    r"venture partner|advisor|adviser|analyst|owner|board|executive|senior|technology investor|at)\b)",
    re.I)


def split_name_headline(name: str) -> tuple[str, str]:
    """'Alex Leibowitz Vice President at Insight' -> ('Alex Leibowitz', 'Vice President at Insight').
    Only splits after at least 2 name words, so 'Head Ventures' style names stay intact."""
    parts = HEADLINE_WORDS.split(name, maxsplit=1)
    if len(parts) > 1 and len(parts[0].split()) >= 2:
        return parts[0].strip(), name[len(parts[0]):].strip()
    return name, ""


def person_key(name: str) -> str:
    """Matching key for people: lower-case letters only, word order kept."""
    s = unicodedata.normalize("NFKD", clean_text(name).lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[^a-z ]", "", re.sub(r"\s+", " ", s)).strip()


# ---------- investor type ----------

# First keyword found wins (order matters: "multi family office" before "family office").
TYPE_RULES = [
    ("Multi-Family Office", ["multi-family", "multi family", "mfo"]),
    ("Family Office", ["family office", "single family", "sfo", "family"]),
    ("Fund of Funds", ["fund of fund", "fund-of-fund", "fof", "funds of funds"]),
    ("Sovereign Wealth", ["sovereign", "swf"]),
    ("Pension", ["pension", "retirement"]),
    ("Endowment", ["endowment", "university"]),
    ("Foundation", ["foundation", "charit", "non-profit", "nonprofit"]),
    ("Insurance", ["insurance", "insurer"]),
    ("Corporate VC", ["corporate", "cvc"]),
    ("Accelerator", ["accelerator", "incubator", "studio"]),
    ("Angel", ["angel", "hnwi", "hnw", "individual", "uhnw", "solo gp", "business angel"]),
    ("Private Equity", ["private equity", "buyout", "pe fund", "growth equity", "pe firm"]),
    ("Venture Capital", ["venture", "vc", "micro vc", "seed fund"]),
    ("Asset Manager", ["asset manag", "wealth manag", "investment manag", "advisor", "adviser", "ria"]),
    ("Bank", ["bank"]),
    ("Hedge Fund", ["hedge"]),
]


def clean_firm_type(value) -> str:
    """Map messy types ('VC fund', 'Single Family Office (SFO)') to one standard list."""
    s = clean_text(value).lower()
    if not s:
        return ""
    for label, words in TYPE_RULES:
        if any(re.search(r"(^|\W)" + re.escape(w), s) for w in words):
            return label
    return "Other"


# Types that by nature invest in funds (i.e. are LPs).
LP_TYPES = {"Fund of Funds", "Sovereign Wealth", "Pension", "Endowment", "Foundation", "Insurance",
            "Family Office", "Multi-Family Office"}


# ---------- lists (sectors, stages) ----------

def merge_lists(values, limit=12) -> str:
    """Combine 'AI, Fintech' + 'fintech; SaaS' -> 'AI, Fintech, SaaS' (no repeats)."""
    seen, out = set(), []
    for v in values:
        for part in re.split(r"[,;|/\n•]+", clean_text(v)):
            p = part.strip(" .-")
            if 1 < len(p) <= 40 and p.lower() not in seen:
                seen.add(p.lower())
                out.append(p)
    return ", ".join(out[:limit])


# ---------- numbers ----------

def clean_money(value) -> str:
    """'$1.5B' -> '1500000000', '250k' -> '250000'; '' if no number."""
    s = clean_text(value).lower().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(bn|billion|b|mm|million|m|k|thousand)?\b", s)
    if not m:
        return ""
    n = float(m.group(1)) * {"bn": 1e9, "billion": 1e9, "b": 1e9, "mm": 1e6, "million": 1e6,
                             "m": 1e6, "k": 1e3, "thousand": 1e3}.get(m.group(2) or "", 1)
    return str(int(n)) if n >= 1000 else ""


def money_range(value) -> tuple[str, str]:
    """'$250k - $1M' -> ('250000', '1000000'); a single amount -> (x, x)."""
    s = clean_text(value).lower().replace(",", "")
    amounts = [clean_money(m.group(0)) for m in
               re.finditer(r"\d+(?:\.\d+)?\s*(?:bn|billion|b|mm|million|m|k|thousand)?\b", s)]
    amounts = [int(a) for a in amounts if a]
    if not amounts:
        return "", ""
    return str(min(amounts)), str(max(amounts))
