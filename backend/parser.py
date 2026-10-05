import re
import pdfplumber

REPORT_PERIOD_RE = re.compile(
    r"Maandbericht\s+(januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december)\s+(\d{4})",
    re.IGNORECASE,
)
ISIN_RE = re.compile(r"\bISIN[:\s]+([A-Z]{2}[A-Z0-9]{9}\d)\b")

DUTCH_MONTHS = {
    "januari": 1, "februari": 2, "maart": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "augustus": 8, "september": 9, "oktober": 10, "november": 11, "december": 12,
}


def parse_pdf(path: str) -> dict:
    pages = []
    full_text_parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            full_text_parts.append(text)
            pages.append({
                "text": text,
                "image_count": len(page.images),
            })
    full_text = "\n".join(full_text_parts)

    period_match = REPORT_PERIOD_RE.search(full_text)
    report_period = None
    if period_match:
        month_name, year = period_match.group(1).lower(), int(period_match.group(2))
        report_period = f"{year}-{DUTCH_MONTHS[month_name]:02d}"

    isin_match = ISIN_RE.search(full_text)
    found_isin = isin_match.group(1) if isin_match else None

    return {
        "pages": pages,
        "full_text": full_text,
        "page_count": len(pages),
        "report_period": report_period,
        "found_isin": found_isin,
    }


def check_components(full_text: str, expected_components: list[str]) -> list[str]:
    missing = []
    for component in expected_components:
        if component.lower() not in full_text.lower():
            missing.append(component)
    return missing
