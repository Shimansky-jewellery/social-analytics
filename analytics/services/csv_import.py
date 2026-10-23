from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import BytesIO
import math
import re

import pandas as pd

MAX_UPLOAD_BYTES = 8 * 1024 * 1024

COLUMN_ALIASES = {
    "channel": {"channel", "social media channel"},
    "period": {"period", "reporting period", "date", "reporting date"},
    "follower_growth": {"follower growth", "followers growth", "follower growths"},
    "reach": {"reach"},
    "views": {"views"},
    "engagement_rate": {"engagement rate", "engagement rate (%)", "engagement rate %"},
    "content_interactions": {"content interactions", "interactions"},
    "ctr": {
        "click-through rate (ctr) (%)",
        "click through rate (ctr) (%)",
        "click-through rate (%)",
        "click through rate (%)",
        "ctr (%)",
        "ctr %",
        "ctr",
    },
    "profile_visits": {"profile visits"},
    "link_clicks": {"link clicks"},
    "leads": {
        "dms/leads generated",
        "dms / leads generated",
        "dms leads generated",
        "leads generated",
        "dms/leads",
        "dms / leads",
    },
    "top_performing_post": {"top performing post", "top-performing post"},
}

NUMERIC_FIELDS = (
    "follower_growth",
    "reach",
    "views",
    "engagement_rate",
    "content_interactions",
    "ctr",
    "profile_visits",
    "link_clicks",
    "leads",
)


class CsvImportError(ValueError):
    pass


@dataclass
class ProcessedImport:
    frame: pd.DataFrame
    rejected: list[dict]
    warnings: list[str]
    total_rows: int


AD_CSV_HEADERS = (
    "Platform",
    "Period Start",
    "Period End",
    "Ad Name",
    "Ad Set",
    "Status",
    "Amount Spent (ZAR)",
    "Impressions",
    "Reach",
    "Frequency",
    "CPM (ZAR)",
    "Results",
    "Result Type",
    "Cost per Result (ZAR)",
    "Quality Ranking",
    "Engagement Rate Ranking",
    "Conversion Rate Ranking",
)

AD_NUMERIC_FIELDS = {
    "Amount Spent (ZAR)": ("amount_spent", "decimal"),
    "Impressions": ("impressions", "integer"),
    "Reach": ("reach", "integer"),
    "Frequency": ("frequency", "float"),
    "CPM (ZAR)": ("cpm", "decimal"),
    "Results": ("results", "float"),
    "Cost per Result (ZAR)": ("cost_per_result", "decimal"),
}


@dataclass
class ProcessedAdImport:
    rows: list[dict]
    rejected: list[dict]
    total_rows: int


def _normalise_header(value):
    text = str(value).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _parse_period(value):
    text = str(value).strip()
    parsed = pd.to_datetime(text, errors="coerce", format="mixed")
    if pd.isna(parsed):
        return text
    if isinstance(parsed, pd.Timestamp):
        return parsed.date().isoformat()
    if isinstance(parsed, date):
        return parsed.isoformat()
    return text


def _parse_number(value):
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "null", "-", "n/a", "na"}:
        return None
    text = text.replace(",", "").replace("%", "").replace("R", "").strip()
    try:
        number = pd.to_numeric(text, errors="raise")
    except (ValueError, TypeError):
        raise ValueError(f"{value!s} is not a valid number")
    if not pd.notna(number):
        return None
    number = float(number)
    if not math.isfinite(number):
        raise ValueError(f"{value!s} must be a finite number")
    return number


def process_dataframe(source):
    if source.empty:
        raise CsvImportError("The file has headers but no data rows.")

    original_headers = list(source.columns)
    normalised_headers = [_normalise_header(header) for header in original_headers]
    if any(not header for header in normalised_headers):
        raise CsvImportError("The CSV contains a blank column heading.")
    if len(set(normalised_headers)) != len(normalised_headers):
        raise CsvImportError("The CSV contains duplicate column headings.")

    source = source.copy()
    source.columns = normalised_headers
    column_map = {}
    warnings = []
    for model_field, aliases in COLUMN_ALIASES.items():
        matching = [header for header in normalised_headers if header in aliases]
        populated = [
            header for header in matching
            if source[header].fillna("").astype(str).str.strip().ne("").any()
        ]
        if len(populated) > 1:
            raise CsvImportError(
                f"Multiple populated columns map to {model_field.replace('_', ' ')}: "
                + ", ".join(populated)
                + ". Keep only one."
            )
        if matching:
            column_map[model_field] = populated[0] if populated else matching[0]
            if len(matching) > 1:
                empty_aliases = [header for header in matching if header not in populated]
                if empty_aliases:
                    warnings_text = (
                        "Ignored empty duplicate headings for "
                        + model_field.replace("_", " ")
                        + ": "
                        + ", ".join(empty_aliases)
                    )
                    warnings.append(warnings_text)

    required_labels = {"channel": "Channel", "period": "Period"}
    missing = [
        required_labels[field]
        for field in required_labels
        if field not in column_map
    ]
    if missing:
        raise CsvImportError("Missing required columns: " + ", ".join(missing) + ".")

    unsupported = [
        header
        for header in normalised_headers
        if header not in {alias for aliases in COLUMN_ALIASES.values() for alias in aliases}
        and source[header].fillna("").astype(str).str.strip().ne("").any()
    ]
    if unsupported:
        raise CsvImportError(
            "Unsupported columns contain data: "
            + ", ".join(unsupported)
            + ". Remove them or map them to a supported column before importing."
        )

    blank_unsupported = [
        header
        for header in normalised_headers
        if header not in {alias for aliases in COLUMN_ALIASES.values() for alias in aliases}
    ]
    if blank_unsupported:
        warnings.append("Ignored empty unsupported columns: " + ", ".join(blank_unsupported))

    rows = []
    rejected = []
    for index, source_row in source.iterrows():
        line_number = index + 2
        row = {field: None for field in COLUMN_ALIASES}
        for field, header in column_map.items():
            row[field] = source_row[header]

        channel = "" if pd.isna(row["channel"]) else str(row["channel"]).strip()
        period = "" if pd.isna(row["period"]) else str(row["period"]).strip()
        row_errors = []
        if not channel or channel.lower() in {"nan", "none", "null"}:
            row_errors.append("Channel is required")
        if not period or period.lower() in {"nan", "none", "null"}:
            row_errors.append("Period is required")
        row["channel"] = channel
        row["period"] = _parse_period(period) if period else ""
        row["top_performing_post"] = (
            "" if pd.isna(row["top_performing_post"]) else str(row["top_performing_post"]).strip()
        )

        for field in NUMERIC_FIELDS:
            try:
                row[field] = _parse_number(row[field])
            except ValueError as exc:
                row_errors.append(f"{field.replace('_', ' ').title()}: {exc}")

        if row_errors:
            rejected.append({"line": line_number, "errors": row_errors})
        else:
            rows.append(row)

    return ProcessedImport(
        frame=pd.DataFrame(rows, columns=list(COLUMN_ALIASES)),
        rejected=rejected,
        warnings=warnings,
        total_rows=len(source),
    )


def process_csv_upload(upload):
    if not upload.name.lower().endswith(".csv"):
        raise CsvImportError("Choose a file with a .csv extension.")
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
    return process_dataframe(frame)


def process_ad_csv_upload(upload):
    if not upload.name.lower().endswith(".csv"):
        raise CsvImportError("Choose an ads file with a .csv extension.")
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

    if tuple(frame.columns) != AD_CSV_HEADERS:
        missing = [header for header in AD_CSV_HEADERS if header not in frame.columns]
        extra = [str(header) for header in frame.columns if header not in AD_CSV_HEADERS]
        details = []
        if missing:
            details.append("missing headers: " + ", ".join(missing))
        if extra:
            details.append("unexpected headers: " + ", ".join(extra))
        if not details:
            details.append("headers must match the required names and order")
        raise CsvImportError("Invalid ads CSV headers (" + "; ".join(details) + ").")
    if frame.empty:
        raise CsvImportError("The file has headers but no data rows.")

    rows = []
    rejected = []
    for index, source_row in frame.iterrows():
        line_number = index + 2
        row = {
            "platform": str(source_row["Platform"]).strip(),
            "ad_name": str(source_row["Ad Name"]).strip(),
            "ad_set": str(source_row["Ad Set"]).strip(),
            "status": str(source_row["Status"]).strip(),
            "result_type": str(source_row["Result Type"]).strip(),
            "quality_ranking": str(source_row["Quality Ranking"]).strip(),
            "engagement_rate_ranking": str(source_row["Engagement Rate Ranking"]).strip(),
            "conversion_rate_ranking": str(source_row["Conversion Rate Ranking"]).strip(),
        }
        errors = []
        for field, label, maximum in (
            ("platform", "Platform", 100),
            ("ad_name", "Ad Name", 255),
        ):
            if not row[field] or row[field].lower() in {"nan", "none", "null"}:
                errors.append(f"{label} is required")
            elif len(row[field]) > maximum:
                errors.append(f"{label} must be {maximum} characters or fewer")
        for field, label, maximum in (
            ("ad_set", "Ad Set", 255),
            ("status", "Status", 50),
            ("result_type", "Result Type", 255),
            ("quality_ranking", "Quality Ranking", 100),
            ("engagement_rate_ranking", "Engagement Rate Ranking", 100),
            ("conversion_rate_ranking", "Conversion Rate Ranking", 100),
        ):
            if len(row[field]) > maximum:
                errors.append(f"{label} must be {maximum} characters or fewer")

        for header, field in (("Period Start", "period_start"), ("Period End", "period_end")):
            raw_date = str(source_row[header]).strip()
            parsed_date = pd.to_datetime(raw_date, errors="coerce", format="mixed")
            if not raw_date or pd.isna(parsed_date):
                errors.append(f"{header} is required and must be a valid date")
            else:
                row[field] = parsed_date.date()
        if "period_start" in row and "period_end" in row and row["period_start"] > row["period_end"]:
            errors.append("Period Start must not be after Period End")

        for header, (field, kind) in AD_NUMERIC_FIELDS.items():
            try:
                value = _parse_number(source_row[header])
                if value is None:
                    row[field] = None
                elif kind == "integer":
                    if not value.is_integer():
                        raise ValueError(f"{source_row[header]!s} must be a whole number")
                    row[field] = int(value)
                elif kind == "decimal":
                    decimal_value = Decimal(str(value))
                    quantized = decimal_value.quantize(Decimal("0.01"))
                    if quantized != decimal_value:
                        raise ValueError(f"{source_row[header]!s} must have at most 2 decimal places")
                    row[field] = quantized
                else:
                    row[field] = value
            except (ValueError, ArithmeticError) as exc:
                errors.append(f"{header}: {exc}")

        if errors:
            rejected.append({"line": line_number, "errors": errors})
        else:
            rows.append(row)

    return ProcessedAdImport(rows=rows, rejected=rejected, total_rows=len(frame))
