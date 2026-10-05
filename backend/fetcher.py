import httpx

FACTSHEET_URL_TEMPLATE = "https://finfiles.vanlanschotkempen.com/nl/pdf/factsheet/{isin}/factsheet_{isin}.pdf"


def fetch_factsheet(isin: str, timeout: float = 30.0) -> bytes:
    """Download the current factsheet for a shareclass. The finfiles.vanlanschotkempen.com
    URL always serves the latest published factsheet for a given ISIN, regardless of
    the filename portion of the path."""
    url = FACTSHEET_URL_TEMPLATE.format(isin=isin)
    with httpx.Client(follow_redirects=True, timeout=timeout) as client:
        resp = client.get(url, headers={"User-Agent": "Mozilla/5.0 (DQ-Monitor POC)"})
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "pdf" not in content_type.lower():
            raise ValueError(f"Expected a PDF for ISIN {isin}, got content-type={content_type!r}")
        return resp.content
