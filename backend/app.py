import json
import os
import hashlib
from datetime import datetime, timezone

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

import db
from fetcher import fetch_factsheet, FACTSHEET_URL_TEMPLATE
from analyzer import analyze

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
PDF_DIR = os.path.join(DATA_DIR, "pdfs")
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")

with open(os.path.join(BASE_DIR, "registry.json"), encoding="utf-8") as f:
    REGISTRY = json.load(f)

with open(os.path.join(BASE_DIR, "templates.json"), encoding="utf-8") as f:
    TEMPLATES = json.load(f)

# Flatten registry into a lookup: isin -> {category, fund_name, klasse_name, template}
SHARECLASSES: dict[str, dict] = {}
for category, cat_def in REGISTRY.items():
    template = cat_def["template"]
    for fund_name, classes in cat_def["funds"].items():
        for klasse_name, isin in classes.items():
            SHARECLASSES[isin] = {
                "isin": isin,
                "category": category,
                "fund_name": fund_name,
                "klasse_name": klasse_name,
                "template": template,
            }

app = FastAPI(title="Factsheet DQ Monitor")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _run_row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "isin": row["isin"],
        "category": row["category"],
        "fund_name": row["fund_name"],
        "klasse_name": row["klasse_name"],
        "fetched_at": row["fetched_at"],
        "report_period": row["report_period"],
        "page_count": row["page_count"],
        "source": row["source"],
        "status": row["status"],
        "error_message": row["error_message"],
    }


def _process_shareclass(isin: str, pdf_bytes: bytes, source: str) -> dict:
    if isin not in SHARECLASSES:
        raise HTTPException(status_code=404, detail=f"Unknown ISIN {isin}, not in registry")
    meta = SHARECLASSES[isin]
    template_def = TEMPLATES[meta["template"]]

    isin_dir = os.path.join(PDF_DIR, isin)
    os.makedirs(isin_dir, exist_ok=True)
    content_hash = hashlib.sha256(pdf_bytes).hexdigest()[:12]
    fetched_at = datetime.now(timezone.utc).isoformat()
    tmp_filename = f"{fetched_at[:19].replace(':', '-')}_{content_hash}.pdf"
    pdf_path = os.path.join(isin_dir, tmp_filename)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    conn = db.get_conn()
    try:
        previous_run = db.get_previous_run(conn, isin)
        try:
            result = analyze(pdf_path, isin, template_def, previous_run)
        except Exception as e:
            run_id = db.insert_run(conn, {
                "isin": isin,
                "category": meta["category"],
                "fund_name": meta["fund_name"],
                "klasse_name": meta["klasse_name"],
                "template": meta["template"],
                "fetched_at": fetched_at,
                "report_period": None,
                "pdf_path": pdf_path,
                "page_count": None,
                "page_image_counts": None,
                "source": source,
                "status": "error",
                "error_message": f"Parse failure: {e}",
            })
            return {"isin": isin, "status": "error", "error_message": str(e)}

        page_image_counts = json.dumps([p["image_count"] for p in result["parsed"]["pages"]])
        run_id = db.insert_run(conn, {
            "isin": isin,
            "category": meta["category"],
            "fund_name": meta["fund_name"],
            "klasse_name": meta["klasse_name"],
            "template": meta["template"],
            "fetched_at": fetched_at,
            "report_period": result["parsed"]["report_period"],
            "pdf_path": pdf_path,
            "page_count": result["parsed"]["page_count"],
            "page_image_counts": page_image_counts,
            "source": source,
            "status": result["status"],
            "error_message": None,
        })
        db.insert_findings(conn, run_id, result["findings"])
        return {
            "isin": isin,
            "run_id": run_id,
            "status": result["status"],
            "findings": result["findings"],
            "report_period": result["parsed"]["report_period"],
        }
    finally:
        conn.close()


@app.on_event("startup")
def startup():
    db.init_db()


@app.get("/api/registry")
def get_registry():
    return REGISTRY


@app.get("/api/dashboard")
def get_dashboard():
    conn = db.get_conn()
    try:
        latest_rows = {row["isin"]: row for row in db.get_latest_runs(conn)}
        categories = {}
        for isin, meta in SHARECLASSES.items():
            cat = meta["category"]
            fund = meta["fund_name"]
            categories.setdefault(cat, {})
            categories[cat].setdefault(fund, [])

            row = latest_rows.get(isin)
            if row is None:
                entry = {
                    "isin": isin,
                    "klasse_name": meta["klasse_name"],
                    "status": "not_run",
                    "report_period": None,
                    "fetched_at": None,
                    "finding_count": 0,
                }
            else:
                findings = db.get_findings_for_run(conn, row["id"])
                entry = {
                    "isin": isin,
                    "klasse_name": meta["klasse_name"],
                    "status": row["status"],
                    "report_period": row["report_period"],
                    "fetched_at": row["fetched_at"],
                    "finding_count": len(findings),
                }
            categories[cat][fund].append(entry)
        return categories
    finally:
        conn.close()


@app.post("/api/fetch/{isin}")
def fetch_one(isin: str):
    if isin not in SHARECLASSES:
        raise HTTPException(status_code=404, detail=f"Unknown ISIN {isin}")
    try:
        pdf_bytes = fetch_factsheet(isin)
    except Exception as e:
        conn = db.get_conn()
        meta = SHARECLASSES[isin]
        db.insert_run(conn, {
            "isin": isin,
            "category": meta["category"],
            "fund_name": meta["fund_name"],
            "klasse_name": meta["klasse_name"],
            "template": meta["template"],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "report_period": None,
            "pdf_path": "",
            "page_count": None,
            "page_image_counts": None,
            "source": "fetch",
            "status": "error",
            "error_message": f"Download failed: {e}",
        })
        conn.close()
        return JSONResponse(status_code=502, content={"isin": isin, "status": "error", "error_message": str(e)})
    return _process_shareclass(isin, pdf_bytes, source="fetch")


@app.post("/api/fetch-all")
def fetch_all():
    results = []
    for isin in SHARECLASSES:
        try:
            pdf_bytes = fetch_factsheet(isin)
            results.append(_process_shareclass(isin, pdf_bytes, source="fetch"))
        except Exception as e:
            meta = SHARECLASSES[isin]
            conn = db.get_conn()
            db.insert_run(conn, {
                "isin": isin,
                "category": meta["category"],
                "fund_name": meta["fund_name"],
                "klasse_name": meta["klasse_name"],
                "template": meta["template"],
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "report_period": None,
                "pdf_path": "",
                "page_count": None,
                "page_image_counts": None,
                "source": "fetch",
                "status": "error",
                "error_message": f"Download failed: {e}",
            })
            conn.close()
            results.append({"isin": isin, "status": "error", "error_message": str(e)})
    summary = {
        "total": len(results),
        "ok": sum(1 for r in results if r["status"] == "ok"),
        "warning": sum(1 for r in results if r["status"] == "warning"),
        "error": sum(1 for r in results if r["status"] == "error"),
        "info": sum(1 for r in results if r["status"] == "info"),
    }
    return {"summary": summary, "results": results}


@app.post("/api/upload")
async def upload(isin: str = Form(...), file: UploadFile = File(...)):
    pdf_bytes = await file.read()
    return _process_shareclass(isin, pdf_bytes, source="upload")


@app.get("/api/shareclass/{isin}")
def get_shareclass(isin: str):
    if isin not in SHARECLASSES:
        raise HTTPException(status_code=404, detail=f"Unknown ISIN {isin}")
    meta = SHARECLASSES[isin]
    conn = db.get_conn()
    try:
        history_rows = db.get_history(conn, isin, limit=12)
        history = []
        for row in history_rows:
            findings = db.get_findings_for_run(conn, row["id"])
            history.append({
                **_run_row_to_dict(row),
                "findings": [dict(f) for f in findings],
            })
        template_def = TEMPLATES[meta["template"]]
        return {
            "meta": meta,
            "live_factsheet_url": FACTSHEET_URL_TEMPLATE.format(isin=isin),
            "expected_components": template_def["components"],
            "expected_page_count": template_def["expected_page_count"],
            "history": history,
        }
    finally:
        conn.close()


@app.get("/api/pdf/{run_id}")
def get_pdf(run_id: int):
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None or not row["pdf_path"] or not os.path.exists(row["pdf_path"]):
            raise HTTPException(status_code=404, detail="PDF not found")
        return FileResponse(row["pdf_path"], media_type="application/pdf")
    finally:
        conn.close()


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
