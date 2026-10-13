from urllib.parse import urlparse, parse_qs
from io import BytesIO
import requests
import pandas as pd

from .csv_import import CsvImportError, ProcessedImport, process_dataframe

MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024
TIMEOUT_SECONDS = 15

class SheetImportError(ValueError):
    pass

def to_csv_export_url(shared_url: str) -> str:
    """Convert a standard Google Sheets URL to a CSV export URL."""
    parsed = urlparse(shared_url.strip())
    if parsed.scheme != "https" or parsed.hostname not in {"docs.google.com"}:
        raise SheetImportError("Please provide an HTTPS Google Sheets link from docs.google.com.")
    parts = [p for p in parsed.path.split("/") if p]
    try:
        spreadsheet_index = parts.index("spreadsheets")
        if parts[spreadsheet_index + 1] != "d":
            raise ValueError
        sheet_id = parts[spreadsheet_index + 2]
    except (ValueError, IndexError):
        raise SheetImportError("That link doesn't look like a Google Sheets spreadsheet URL.")
    if not sheet_id or not all(c.isalnum() or c in "-_" for c in sheet_id):
        raise SheetImportError("The spreadsheet ID in that link is invalid.")

    query = parse_qs(parsed.query)
    gid = query.get("gid", ["0"])[0]
    if not gid.isdigit():
        gid = "0"
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"

def fetch_sheet_dataframe(shared_url: str) -> ProcessedImport:
    csv_url = to_csv_export_url(shared_url)
    try:
        response = requests.get(
            csv_url,
            timeout=TIMEOUT_SECONDS,
            headers={"User-Agent": "SocialInsightsDashboard/1.0"},
            stream=True,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise SheetImportError("Could not connect to Google Sheets. Check the link and try again.") from exc

    if response.status_code in (301, 302, 303, 307, 308):
        raise SheetImportError("Google redirected the request. Publish the sheet to the web as CSV, then try again.")
    if response.status_code != 200:
        raise SheetImportError(
            "Google Sheets did not allow access. Make the sheet viewable without signing in or publish it to the web."
        )

    content = bytearray()
    for chunk in response.iter_content(chunk_size=65536):
        content.extend(chunk)
        if len(content) > MAX_DOWNLOAD_BYTES:
            raise SheetImportError("The sheet export is too large (maximum 8 MB).")
    if not content:
        raise SheetImportError("The exported sheet was empty.")

    try:
        frame = pd.read_csv(BytesIO(content), encoding="utf-8-sig", keep_default_na=False)
        return process_dataframe(frame)
    except (CsvImportError, pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError, ValueError) as exc:
        raise SheetImportError(str(exc) or "The sheet export was not a readable CSV.") from exc
