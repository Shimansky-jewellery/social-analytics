from dataclasses import dataclass
from datetime import date
from io import BytesIO

import pandas as pd

from .csv_import import MAX_UPLOAD_BYTES, CsvImportError, _parse_number

AUDIENCE_CSV_HEADERS = (
    "Channel",
    "Snapshot Date",
    "Category",
    "Label",
    "Segment",
    "Value",
    "Unit",
)


@dataclass
class ProcessedAudienceImport:
    rows: list[dict]
    rejected: list[dict]
    total_rows: int


def process_audience_csv_upload(upload):
    if not upload.name.lower().endswith(".csv"):
        raise CsvImportError("Choose an audience file with a .csv extension.")
    if upload.size > MAX_UPLOAD_BYTES:
        raise CsvImportError("The CSV file is too large. The maximum upload size is 8 MB.")
    content = upload.read(MAX_UPLOAD_BYTES + 1)
    if not content:
        raise CsvImportError("The selected CSV file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise CsvImportError("The CSV file is too large. The maximum upload size is 8 MB.")

    try:
        frame = pd.read_csv(BytesIO(content), encoding="utf-8-sig", keep_default_na=False)
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError, ValueError) as exc:
        raise CsvImportError(
            "The file could not be read as a CSV. Check its encoding and column structure."
        ) from exc

    if tuple(frame.columns) != AUDIENCE_CSV_HEADERS:
        missing = [header for header in AUDIENCE_CSV_HEADERS if header not in frame.columns]
        extra = [str(header) for header in frame.columns if header not in AUDIENCE_CSV_HEADERS]
        details = []
        if missing:
            details.append("missing headers: " + ", ".join(missing))
        if extra:
            details.append("unexpected headers: " + ", ".join(extra))
        if not details:
            details.append("headers must match the required names and order")
        raise CsvImportError("Invalid audience CSV headers (" + "; ".join(details) + ").")
    if frame.empty:
        raise CsvImportError("The file has headers but no data rows.")

    rows = []
    rejected = []
    for index, source_row in frame.iterrows():
        line_number = index + 2
        row = {
            "channel": str(source_row["Channel"]).strip(),
            "category": str(source_row["Category"]).strip(),
            "label": str(source_row["Label"]).strip(),
            "segment": str(source_row["Segment"]).strip(),
            "unit": str(source_row["Unit"]).strip(),
        }
        errors = []
        for field, header, max_length in (
            ("channel", "Channel", 100),
            ("category", "Category", 100),
            ("label", "Label", 255),
        ):
            if not row[field] or row[field].lower() in {"nan", "none", "null"}:
                errors.append(f"{header} is required")
            elif len(row[field]) > max_length:
                errors.append(f"{header} must be {max_length} characters or fewer")
        if len(row["segment"]) > 100:
            errors.append("Segment must be 100 characters or fewer")
        if len(row["unit"]) > 50:
            errors.append("Unit must be 50 characters or fewer")

        raw_date = str(source_row["Snapshot Date"]).strip()
        parsed_date = pd.to_datetime(raw_date, errors="coerce", format="mixed")
        if not raw_date or pd.isna(parsed_date):
            errors.append("Snapshot Date is required and must be a valid date")
        else:
            row["snapshot_date"] = date(parsed_date.year, parsed_date.month, parsed_date.day)

        try:
            value = _parse_number(source_row["Value"])
            if value is None:
                errors.append("Value is required and must be a valid number")
            else:
                row["value"] = value
        except ValueError as exc:
            errors.append(f"Value: {exc}")

        if errors:
            rejected.append({"line": line_number, "errors": errors})
        else:
            rows.append(row)

    return ProcessedAudienceImport(rows=rows, rejected=rejected, total_rows=len(frame))
