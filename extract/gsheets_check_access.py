"""
gsheets_check_access.py - test which Google Sheets from the source list we can open.

For every Google Sheets link in the Notion export it:
  1. pulls out the sheet's ID (the long code in the link),
  2. tries to open it with your Google login (read-only),
  3. records the tabs inside it and roughly how many rows each has.

Output: data/raw/gsheets/access_report.csv  (one row per unique sheet)
Reads AS YOU (your Google login, see extract/google_auth.py). Uploaded Excel
files can't be opened as Google Sheets, so for those we ask Google Drive instead.

Run:    .venv/Scripts/python -m extract.gsheets_check_access
"""
import csv
import os
import re
import time
from pathlib import Path

import gspread
import openpyxl
from dotenv import load_dotenv
from googleapiclient.discovery import build

from extract.google_auth import get_creds, get_gspread

load_dotenv()
SOURCE_FILE = Path.home() / "Downloads" / "Data_sources_Notion_export.xlsx"
OUT = Path("data/raw/gsheets/access_report.csv")
SHEET_ID = re.compile(r"docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]{20,})")


def collect_links():
    """Return {sheet_id: {"names": [...], "types": [...], "url": first link seen}}."""
    ws = openpyxl.load_workbook(SOURCE_FILE, read_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    col = {name: i for i, name in enumerate(header)}
    found = {}
    for r in rows[1:]:
        if not r or not r[0]:
            continue
        for field in ("Link", "Link to raw data"):
            cell = str(r[col[field]] or "") if col[field] < len(r) else ""
            for sid in SHEET_ID.findall(cell):
                entry = found.setdefault(sid, {"names": [], "types": set(), "url": cell})
                if r[0] not in entry["names"]:
                    entry["names"].append(r[0])
                stype = r[col["Source type"]] if col["Source type"] < len(r) else None
                if stype:
                    entry["types"].add(str(stype))
    return found


def main():
    links = collect_links()
    print(f"Unique Google Sheets in source list: {len(links)}")
    client = get_gspread()
    drive = build("drive", "v3", credentials=get_creds())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    ok = 0
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sheet_id", "source_names", "source_type", "status", "title", "tabs", "total_rows", "error", "url"])
        for i, (sid, info) in enumerate(links.items(), 1):
            status, title, tabs, total, err = "ok", "", "", 0, ""
            try:
                book = client.open_by_key(sid)
                title = book.title
                worksheets = book.worksheets()
                tabs = " | ".join(f"{s.title} ({s.row_count})" for s in worksheets)
                total = sum(s.row_count for s in worksheets)
                ok += 1
            except (gspread.exceptions.APIError, gspread.exceptions.SpreadsheetNotFound, PermissionError) as e:
                # Not a Google Sheet we can open - ask Drive what the file is.
                try:
                    meta = drive.files().get(fileId=sid, fields="name,mimeType,size",
                                             supportsAllDrives=True).execute()
                    title = meta["name"]
                    status = "excel_file" if "spreadsheetml" in meta["mimeType"] or "excel" in meta["mimeType"]                         else "drive_" + meta["mimeType"].split("/")[-1][:20]
                    ok += 1
                except Exception as e2:
                    code = getattr(getattr(e2, "resp", None), "status", "")
                    status = {403: "no_access", 404: "not_found"}.get(code, "no_access")
                    err = f"{type(e).__name__} / {e2}"[:150]
            except Exception as e:  # anything unexpected: record it, keep going
                status, err = "error", f"{type(e).__name__}: {e}"[:150]
            w.writerow([sid, " ; ".join(info["names"]), " ; ".join(sorted(info["types"])),
                        status, title, tabs, total, err, info["url"]])
            print(f"[{i}/{len(links)}] {status:10} {title[:50] or info['names'][0][:50]}", flush=True)
            time.sleep(1.2)  # stay well under Google's free rate limit
    print(f"\nOpened {ok} of {len(links)}. Report: {OUT}")


if __name__ == "__main__":
    main()
