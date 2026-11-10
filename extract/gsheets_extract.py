"""
gsheets_extract.py - EXTRACT step for Google Sheets.

Reads the access report (made by gsheets_check_access.py) and, for every sheet
we can open, saves EVERY tab as its own untouched CSV file. No cleaning here:
"raw" means exactly what the source had, so we can always go back to it.

  - Google Sheets  -> read each tab through the Sheets API
  - Excel files on Drive -> download the .xlsx, then save each tab as CSV

Output:
  data/raw/gsheets/files/<short id>__<sheet title>__<tab>.csv
  data/raw/gsheets/manifest.csv   (one row per CSV: where it came from, rows, columns)

Safe to re-run: files that already exist are skipped.
Run:  .venv/Scripts/python -m extract.gsheets_extract
"""
import csv
import io
import re
import time
from pathlib import Path

import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from extract.google_auth import get_creds, get_gspread

REPORT = Path("data/raw/gsheets/access_report.csv")
OUT_DIR = Path("data/raw/gsheets/files")
MANIFEST = Path("data/raw/gsheets/manifest.csv")
PAUSE = 1.1   # seconds between Google requests (free limit is 60 reads/minute)


def safe(text: str, n: int = 40) -> str:
    """Make text safe to use in a file name."""
    return re.sub(r"[^A-Za-z0-9]+", "_", str(text)).strip("_")[:n] or "untitled"


def save_rows(path: Path, rows) -> tuple[int, int]:
    """Write a list of rows to CSV; return (data rows, columns)."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    return max(len(rows) - 1, 0), max((len(r) for r in rows), default=0)


def extract_google_sheet(client, sid, title):
    """Yield (tab name, file path, rows, cols) for each tab of a Google Sheet."""
    book = client.open_by_key(sid)
    for ws in book.worksheets():
        path = OUT_DIR / f"{sid[:8]}__{safe(title)}__{safe(ws.title, 30)}.csv"
        if path.exists():
            yield ws.title, path, None, None
            continue
        time.sleep(PAUSE)
        rows = ws.get_all_values()          # every cell, as text
        # drop completely empty rows at the end
        while rows and not any(c.strip() for c in rows[-1]):
            rows.pop()
        r, c = save_rows(path, rows)
        yield ws.title, path, r, c


def extract_excel_file(drive, sid, title):
    """Download an Excel file from Drive and yield each tab like above."""
    buf = io.BytesIO()
    request = drive.files().get_media(fileId=sid, supportsAllDrives=True)
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buf.seek(0)
    for tab, df in pd.read_excel(buf, sheet_name=None, header=None, dtype=str).items():
        path = OUT_DIR / f"{sid[:8]}__{safe(title)}__{safe(tab, 30)}.csv"
        if path.exists():
            yield tab, path, None, None
            continue
        df = df.dropna(how="all")
        rows = df.fillna("").values.tolist()
        r, c = save_rows(path, rows)
        yield tab, path, r, c


def main():
    report = pd.read_csv(REPORT)
    todo = report[report.status.isin(["ok", "excel_file"])]
    print(f"Extracting {len(todo)} files...")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = get_gspread()
    drive = build("drive", "v3", credentials=get_creds())

    manifest = []
    for i, r in enumerate(todo.itertuples(), 1):
        title = r.title if isinstance(r.title, str) else r.source_names
        try:
            tabs = (extract_excel_file(drive, r.sheet_id, title) if r.status == "excel_file"
                    else extract_google_sheet(client, r.sheet_id, title))
            n_tabs = 0
            for tab, path, rows, cols in tabs:
                n_tabs += 1
                manifest.append({
                    "file": path.name, "sheet_id": r.sheet_id, "sheet_title": title, "tab": tab,
                    "source_names": r.source_names, "source_type": r.source_type,
                    "rows": rows, "cols": cols, "url": r.url,
                })
            print(f"[{i}/{len(todo)}] ok    {n_tabs} tab(s)  {str(title)[:60]}", flush=True)
        except Exception as e:  # one bad file shouldn't stop the rest
            print(f"[{i}/{len(todo)}] FAIL  {str(title)[:60]}  ({type(e).__name__}: {str(e)[:80]})", flush=True)
        time.sleep(PAUSE)

    # Keep counts from earlier runs for files that were skipped this time.
    old = pd.read_csv(MANIFEST) if MANIFEST.exists() else pd.DataFrame(columns=["file", "rows", "cols"])
    new = pd.DataFrame(manifest)
    for col in ("rows", "cols"):
        new[col] = new[col].fillna(new.file.map(old.set_index("file")[col]) if len(old) else None)
    new.to_csv(MANIFEST, index=False)
    print(f"\nDone: {len(new)} tabs saved. Manifest: {MANIFEST}")


if __name__ == "__main__":
    main()
