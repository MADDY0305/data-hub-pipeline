"""
google_auth.py - log in to Google AS YOU (read-only), so the pipeline can read
every sheet your work account can open.

First run: a browser window opens -> you sign in -> click "Allow".
Google then gives us a token, saved in google_token.json (secret, git-ignored),
so you won't need to log in again.

Permissions asked for (READ-ONLY - nothing can be edited or deleted):
  - spreadsheets.readonly : read Google Sheets
  - drive.readonly        : download Excel files stored on Drive

Usage in other scripts:
    from extract.google_auth import get_creds, get_gspread
"""
from pathlib import Path

import gspread
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

CLIENT_FILE = Path("google_oauth_client.json")   # the "login key" you download
TOKEN_FILE = Path("google_token.json")           # created after your first login
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def get_creds() -> Credentials:
    """Return valid login credentials, asking you to log in only if needed."""
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())               # silently renew an old token
    else:
        if not CLIENT_FILE.exists():
            raise SystemExit("google_oauth_client.json is missing - see SETUP.md step 3b.")
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES)
        creds = flow.run_local_server(port=0)  # opens your browser to log in
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return creds


def get_gspread() -> gspread.Client:
    """A Google Sheets client that reads as you."""
    return gspread.authorize(get_creds())


if __name__ == "__main__":
    # Quick test: log in and show who we are.
    from googleapiclient.discovery import build
    about = build("drive", "v3", credentials=get_creds()).about().get(fields="user").execute()
    print("Logged in as:", about["user"]["emailAddress"])
