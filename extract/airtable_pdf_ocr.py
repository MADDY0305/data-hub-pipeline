"""
airtable_pdf_ocr.py - turn the Airtable "Print view" PDFs into CSV tables.

WHY: Airtable's print-to-PDF draws text as shapes, not letters, so a computer
can't simply read it. We use OCR (free software that reads text from images).

HOW IT WORKS, page by page:
  1. pdfplumber finds the table GRID (the lines around each cell).
  2. The page is turned into an image, and OCR reads every piece of text
     plus WHERE it sits on the page.
  3. Each piece of text is dropped into the grid cell it falls inside.
  4. The first row is the header (column names); repeated headers on later
     pages are skipped.
  5. The Airtable link printed at the bottom of each page is kept as the source.

Pages with no grid (card layouts) are saved as plain text instead.

Run:   .venv/Scripts/python extract/airtable_pdf_ocr.py            (all PDFs)
       .venv/Scripts/python extract/airtable_pdf_ocr.py 2 5        (only 2.pdf and 5.pdf)
Output: data/raw/airtable/ocr/<n>.csv  (or <n>.txt for card layouts)
It skips PDFs that already have output, so it's safe to stop and re-run.
"""
import csv
import re
import sys
import time
from pathlib import Path

import numpy as np
import pdfplumber
from rapidocr_onnxruntime import RapidOCR

IN_DIR = Path("data/raw/airtable")
OUT_DIR = IN_DIR / "ocr"
DPI = 150                 # image sharpness; 150 is a good speed/accuracy balance
SCALE = DPI / 72          # PDF positions are in "points" (72 per inch)

ocr = RapidOCR()


def read_page(page):
    """OCR one page. Returns a list of (x_center, y_center, text) in PDF points."""
    img = np.array(page.to_image(resolution=DPI).original.convert("RGB"))
    result, _ = ocr(img)
    items = []
    for box, text, _conf in result or []:
        xs = [pt[0] for pt in box]
        ys = [pt[1] for pt in box]
        items.append(((min(xs) + max(xs)) / 2 / SCALE, (min(ys) + max(ys)) / 2 / SCALE, text.strip()))
    return items


def find_source_url(items, page_height):
    """The page footer holds the Airtable link the PDF was printed from."""
    for x, y, text in items:
        if y > page_height * 0.9 and "airtable.com" in text:
            # OCR sometimes reads "https://" as "https:/" - normalise it.
            return "https://" + re.sub(r"^https?:/*", "", text.replace(" ", ""))
    return ""


def page_to_rows(page, items):
    """Put OCR text into the table grid. Returns a list of rows (lists of cell text)."""
    tables = page.find_tables()
    if not tables:
        return None
    rows_out = []
    for table in tables:
        for row in table.rows:
            cells = []
            for cell in row.cells:
                if cell is None:
                    cells.append("")
                    continue
                x0, top, x1, bottom = cell
                # Text whose centre lies inside this cell, in reading order.
                inside = sorted(
                    (it for it in items if x0 <= it[0] <= x1 and top <= it[1] <= bottom),
                    key=lambda it: (round(it[1] / 4), it[0]),
                )
                cells.append(" ".join(t for _, _, t in inside).strip())
            rows_out.append(cells)
    return rows_out


def process_pdf(pdf_path: Path):
    n = pdf_path.stem
    csv_path, txt_path = OUT_DIR / f"{n}.csv", OUT_DIR / f"{n}.txt"
    if csv_path.exists() or txt_path.exists():
        print(f"{n}.pdf: already done, skipping")
        return
    try:
        pdf = pdfplumber.open(pdf_path)
    except Exception as e:
        print(f"{n}.pdf: CAN'T OPEN ({type(e).__name__}) - file is broken, re-download it")
        return

    started, header, data_rows, plain_text, source_url = time.time(), None, [], [], ""
    with pdf:
        total = len(pdf.pages)
        for i, page in enumerate(pdf.pages, start=1):
            items = read_page(page)
            source_url = source_url or find_source_url(items, page.height)
            rows = page_to_rows(page, items)
            if rows is None:  # no grid: keep the raw text, top-to-bottom
                plain_text += [t for _, _, t in sorted(items, key=lambda it: (round(it[1] / 4), it[0]))]
            else:
                for r in rows:
                    if header is None:
                        header = r
                    elif r == header or (r and r[0] == header[0] and r[1:2] == header[1:2]):
                        continue  # repeated header on a new page
                    elif any(c for c in r):
                        data_rows.append(r)
            if i % 10 == 0 or i == total:
                print(f"{n}.pdf: page {i}/{total}  ({time.time() - started:.0f}s)", flush=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if header:
        # Drop Airtable's "#" row-number column; add where the data came from.
        keep = [j for j, h in enumerate(header) if h.strip() not in ("#", "")]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([header[j] for j in keep] + ["source_url"])
            for r in data_rows:
                w.writerow([r[j] if j < len(r) else "" for j in keep] + [source_url])
        print(f"{n}.pdf: DONE -> {csv_path.name}, {len(data_rows)} rows, columns: {[header[j] for j in keep]}")
    else:
        txt_path.write_text(f"source_url: {source_url}\n" + "\n".join(plain_text), encoding="utf-8")
        print(f"{n}.pdf: DONE -> {txt_path.name} (card layout, plain text)")


if __name__ == "__main__":
    wanted = sys.argv[1:]
    pdfs = sorted(IN_DIR.glob("*.pdf"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
    for p in pdfs:
        if not wanted or p.stem in wanted:
            process_pdf(p)
