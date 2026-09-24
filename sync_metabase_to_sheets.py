"""
Sync Metabase dashboard 676 (Assignment Tracker) questions into a Google Sheet.

Each question goes to its own tab. Tabs are created if missing; existing tabs
are fully replaced on every run (header + all rows).

Required environment variables (set as GitHub Actions secrets):
  METABASE_API_KEY   Metabase API key
  GCP_SA_JSON        Full JSON of the Google service account key
                     (share the sheet with the service account email as Editor)
"""

import csv
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import gspread
import requests

# ---------------------------------------------------------------- config ---
METABASE_URL = "https://metabase-lierhfgoeiwhr.newtonschool.co"
SPREADSHEET_ID = "1qJtaFWYCiTPDq-34gbyx78wb3D1ampCv05ftvteMrMk"

# Metabase question id -> tab name in the sheet
QUESTIONS = [
    (12999, "Batchwise Summary"),
    (13000, "Batch User Summary"),
    (13001, "Batch Assignment Summary"),
    (13002, "Student Assignment Detail"),
]

CHUNK_ROWS = 5000          # rows per Sheets write request
EXPORT_TIMEOUT = 900       # seconds to wait for a Metabase export
IST = timezone(timedelta(hours=5, minutes=30))
# ---------------------------------------------------------------------------


def log(msg: str) -> None:
    print(f"[{datetime.now(IST):%Y-%m-%d %H:%M:%S} IST] {msg}", flush=True)


def fetch_question_csv(card_id: int, api_key: str) -> list[list[str]]:
    """Export a saved question as CSV (no 2,000-row limit) and parse it."""
    url = f"{METABASE_URL}/api/card/{card_id}/query/csv"
    headers = {"x-api-key": api_key}
    # format_rows=false -> raw values (ISO timestamps, plain numbers)
    data = {"format_rows": "false", "pivot_results": "false", "parameters": "[]"}

    for attempt in range(1, 4):
        try:
            resp = requests.post(url, headers=headers, data=data, timeout=EXPORT_TIMEOUT)
            if resp.status_code in (200, 202):
                break
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")
        except Exception as exc:  # network error or bad status
            if attempt == 3:
                raise RuntimeError(f"Metabase export failed for question {card_id}: {exc}") from exc
            log(f"  question {card_id}: attempt {attempt} failed ({exc}); retrying")
            time.sleep(15 * attempt)

    text = resp.content.decode("utf-8-sig")  # strip BOM if present
    if text.lstrip().startswith("{"):
        # Metabase returns JSON instead of CSV when the query itself errors
        raise RuntimeError(f"Question {card_id} returned an error: {text[:500]}")

    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise RuntimeError(f"Question {card_id} returned no header row")
    return rows


NUM_RE = re.compile(r"^-?\d+(\.\d+)?$")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")


def clean(value: str):
    """Numbers -> numbers, ISO timestamps -> 'YYYY-MM-DD HH:MM:SS' IST,
    and stop text from being read as a formula."""
    if value == "":
        return ""
    if NUM_RE.match(value):
        return int(value) if "." not in value else float(value)
    if TS_RE.match(value):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                dt = dt.astimezone(IST)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return value
    if value[0] in "=+@":
        return "'" + value
    return value


def get_or_create_tab(sh: gspread.Spreadsheet, title: str, rows: int, cols: int) -> gspread.Worksheet:
    try:
        ws = sh.worksheet(title)
        log(f"  tab '{title}' exists")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=max(rows, 1), cols=max(cols, 1))
        log(f"  tab '{title}' created")
    return ws


def write_tab(ws: gspread.Worksheet, rows: list[list]) -> None:
    n_rows, n_cols = len(rows), len(rows[0])

    # Exact size: removes stale rows/cols from a previous, larger run
    ws.clear()
    ws.resize(rows=max(n_rows, 2), cols=n_cols)  # >=2 so the header can be frozen

    for start in range(0, n_rows, CHUNK_ROWS):
        chunk = rows[start:start + CHUNK_ROWS]
        top = start + 1
        ws.update(
            values=chunk,
            range_name=f"A{top}",
            value_input_option="USER_ENTERED",  # lets Sheets parse dates
        )

    ws.freeze(rows=1)


def main() -> int:
    api_key = os.environ.get("METABASE_API_KEY")
    sa_json = os.environ.get("GCP_SA_JSON")
    if not api_key or not sa_json:
        log("Missing METABASE_API_KEY or GCP_SA_JSON environment variable")
        return 1

    gc = gspread.service_account_from_dict(
        json.loads(sa_json), http_client=gspread.BackOffHTTPClient
    )
    sh = gc.open_by_key(SPREADSHEET_ID)
    log(f"Opened sheet: {sh.title}")

    failures = []
    for card_id, tab in QUESTIONS:
        log(f"Question {card_id} -> '{tab}'")
        try:
            raw = fetch_question_csv(card_id, api_key)
            header, body = raw[0], raw[1:]
            rows = [header] + [[clean(v) for v in r] for r in body]
            log(f"  fetched {len(body):,} rows x {len(header)} cols")

            ws = get_or_create_tab(sh, tab, len(rows), len(header))
            write_tab(ws, rows)
            log(f"  written")
        except Exception as exc:
            log(f"  FAILED: {exc}")
            failures.append(tab)

    if failures:
        log(f"Finished with failures: {', '.join(failures)}")
        return 1
    log("All tabs updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
