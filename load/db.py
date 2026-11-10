"""
db.py - one place that connects to the Supabase warehouse.
Every other script does:   from load.db import get_engine
"""
import os
from urllib.parse import quote
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()  # reads the .env file into environment variables


def _safe_url(raw: str) -> str:
    """Make the connection link safe even if the password has symbols like @ # /.

    A link looks like:  postgresql://USER:PASSWORD@HOST:PORT/DB
    A password containing '@' confuses the computer about where the host starts.
    The host never contains '@', so we split at the LAST '@', then 'escape'
    the password (e.g. '@' becomes '%40') so it's read correctly.
    """
    raw = raw.strip()
    _scheme, rest = raw.split("://", 1)
    credentials, host_part = rest.rsplit("@", 1)
    user, password = credentials.split(":", 1)
    return f"postgresql+psycopg2://{user}:{quote(password, safe='')}@{host_part}"


def get_engine():
    """Return a connection 'engine' to the warehouse."""
    raw = os.environ.get("SUPABASE_DB_URL", "")
    if not raw:
        raise SystemExit("SUPABASE_DB_URL is empty in .env - see SETUP.md step 2.")
    return create_engine(_safe_url(raw), connect_args={"connect_timeout": 15})
