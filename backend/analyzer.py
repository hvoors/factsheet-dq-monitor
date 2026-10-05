import json
from parser import parse_pdf, check_components


def analyze(pdf_path: str, expected_isin: str, template_def: dict, previous_run) -> dict:
    """Parse a factsheet PDF and produce a list of findings plus raw parse data."""
    parsed = parse_pdf(pdf_path)
    findings = []

    missing = check_components(parsed["full_text"], template_def["components"])
    for component in missing:
        findings.append({
            "severity": "warning",
            "code": "missing_component",
            "message": f'Expected section "{component}" was not found in this factsheet.',
        })

    expected_pages = template_def["expected_page_count"]
    if parsed["page_count"] < expected_pages:
        findings.append({
            "severity": "warning",
            "code": "page_count_low",
            "message": f'Factsheet has {parsed["page_count"]} pages, expected at least {expected_pages}.',
        })

    if parsed["found_isin"] and parsed["found_isin"] != expected_isin:
        findings.append({
            "severity": "error",
            "code": "isin_mismatch",
            "message": f'Factsheet content ISIN "{parsed["found_isin"]}" does not match expected "{expected_isin}".',
        })

    if previous_run is not None and parsed["report_period"]:
        if previous_run["report_period"] == parsed["report_period"]:
            findings.append({
                "severity": "info",
                "code": "stale_report",
                "message": f'Report period ({parsed["report_period"]}) is unchanged since the last successful run — a new factsheet may not have been published yet.',
            })

    if previous_run is not None and previous_run["page_image_counts"]:
        prev_counts = json.loads(previous_run["page_image_counts"])
        curr_counts = [p["image_count"] for p in parsed["pages"]]
        for i, prev_count in enumerate(prev_counts):
            curr_count = curr_counts[i] if i < len(curr_counts) else 0
            if prev_count >= 2 and curr_count == 0:
                findings.append({
                    "severity": "warning",
                    "code": "chart_count_drop",
                    "message": f"Page {i + 1} had {prev_count} chart image(s) last run but has none now.",
                })

    if any(f["severity"] == "error" for f in findings):
        status = "error"
    elif any(f["severity"] == "warning" for f in findings):
        status = "warning"
    elif any(f["severity"] == "info" for f in findings):
        status = "info"
    else:
        status = "ok"

    return {
        "parsed": parsed,
        "findings": findings,
        "status": status,
    }
