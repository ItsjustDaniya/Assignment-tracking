# Assignment Tracker → Google Sheets

A GitHub Actions job exports the 4 questions on Metabase dashboard **676 – Assignment Tracker**
into this Google Sheet, one tab per question:

| Metabase question | Tab |
|---|---|
| 12999 – Batchwise Assignment Completion | `Batchwise Summary` |
| 13000 – Batch User Wise Assignment Tracker | `Batch User Summary` |
| 13001 – Batch Assignment Wise Completion Tracker | `Batch Assignment Summary` |
| 13002 – Student Assignment Detail | `Student Assignment Detail` |

Tabs are created if they don't exist, and fully replaced on every run.
Runs **every 3 hours** (02:00, 05:00, 08:00, 11:00, 14:00, 17:00, 20:00, 23:00 IST), and on demand from **Actions → Sync Assignment Tracker → Run workflow**.

## Setup (one time)

1. **Share the sheet** with the service account's `client_email` (from the JSON key) as **Editor**.
2. In the GitHub repo: **Settings → Secrets and variables → Actions → New repository secret**
   - `METABASE_API_KEY` – the Metabase API key
   - `GCP_SA_JSON` – paste the full contents of the service account JSON file
3. The Metabase API key's group needs view + native query access to the Newton School database
   and to the collection holding the 4 questions.
4. Google Cloud project of the service account must have the **Google Sheets API** enabled.

## Changing things

Edit the top of `sync_metabase_to_sheets.py`:
- `QUESTIONS` – question IDs and tab names
- `SPREADSHEET_ID`, `METABASE_URL`

Edit `.github/workflows/sync.yml` → `cron` to change the schedule (it is in UTC).

## Run locally

```bash
pip install -r requirements.txt
export METABASE_API_KEY=...
export GCP_SA_JSON="$(cat service-account.json)"
python sync_metabase_to_sheets.py
```
