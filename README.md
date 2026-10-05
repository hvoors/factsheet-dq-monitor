# Factsheet DQ Monitor

A data-quality monitoring dashboard for Van Lanschot Kempen's monthly fund
factsheets. It fetches the current factsheet PDF for each tracked
shareclass, checks it against a per-fund-type template of sections that
should always be present, and flags anything that's missing, gone stale, or
otherwise looks off before it reaches a client.

## Why

Factsheets are generated and published by a third party without a QC step.
In August 2026 several shareclasses were published with entire sections
(e.g. the annualised performance bar charts) silently missing. This tool
exists to catch that kind of defect automatically after each month's
upload.

## How it works

1. **Registry** (`backend/registry.json`) — the shareclasses in scope:
   Smallcaps, Hoog Dividend, Value, Vastgoed, Infrastructuur and Credits
   (~74 shareclasses across ~20 funds).
2. **Fetch** (`backend/fetcher.py`) — downloads
   `https://finfiles.vanlanschotkempen.com/nl/pdf/factsheet/{ISIN}/...pdf`,
   which always serves that shareclass's *current* factsheet regardless of
   the filename used.
3. **Parse** (`backend/parser.py`) — extracts text and per-page embedded
   image counts with `pdfplumber`.
4. **Check** (`backend/analyzer.py`) against a template
   (`backend/templates.json`) of expected section headers per fund type
   (equity funds vs. credit funds have different normal layouts — verified
   against real factsheets). Flags:
   - `missing_component` — an expected section header isn't in the text
   - `page_count_low` — fewer pages than the template expects
   - `isin_mismatch` — the ISIN printed in the PDF doesn't match the
     shareclass it was fetched for
   - `stale_report` — the report period hasn't advanced since the last run
     (info-level: the new month may not be published yet)
   - `chart_count_drop` — a page that used to have charts now has none
5. **Dashboard** (`frontend/`) — a status grid grouped by category → fund →
   shareclass, with a detail drawer per shareclass showing findings,
   expected components, and history with links to the stored PDFs.

## Setup

Already done once in this environment: a `.venv` with dependencies from
`backend/requirements.txt` installed via
`C:\Users\bssch\AppData\Local\Programs\Python\Python312\python.exe`.

To rebuild from scratch:

```bash
"C:\Users\bssch\AppData\Local\Programs\Python\Python312\python.exe" -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

## Running

```powershell
.\run.ps1
```

Then open http://127.0.0.1:8420 in a browser.

- **Fetch latest for all funds** — hits the live site for all ~74
  shareclasses and re-analyzes them. This is the manual trigger you run
  once you know the new month's factsheets are live.
- **Upload PDF manually** — drag-and-drop fallback for a single shareclass,
  useful if the live fetch is unavailable or you want to pre-check a PDF.

## Data

Downloaded PDFs and the SQLite database (`data/dq_monitor.db`) are stored
under `data/`, which is gitignored. `fixtures/` holds three sample
factsheets used to validate the detection logic:

- `LU0427929855_2026-07.pdf` — a normal Kempen Global High Dividend Fund I
  factsheet
- `LU0427929855_2026-08.pdf` — the same shareclass a month later, with the
  "Rendement in %" section missing (the real incident that motivated this
  tool)
- `LU0630255346_2026-08.pdf` — a credit fund factsheet, used to confirm the
  credit template's different expected sections

## Extending

- Add shareclasses by editing `backend/registry.json`.
- Add or adjust expected sections per fund type in `backend/templates.json`.
- The automatic-fetch trigger is currently manual (a button click, or call
  `POST /api/fetch-all`); wiring it to a schedule (e.g. Windows Task
  Scheduler calling that endpoint, or a cron skill) is the natural next
  step once this POC is validated.
