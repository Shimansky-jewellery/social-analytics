import logging

import pandas as pd
from django.contrib import messages
from django.db import transaction
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .models import SocialMetric
from .services.csv_import import CsvImportError, process_csv_upload
from .services.google_sheets import fetch_sheet_dataframe, SheetImportError
from .services.insights import build_insights, build_period_changes, build_period_series

logger = logging.getLogger(__name__)

METRIC_FIELDS = (
    "follower_growth",
    "reach",
    "views",
    "engagement_rate",
    "content_interactions",
    "profile_visits",
    "link_clicks",
    "leads",
)


def _database_frame():
    rows = list(SocialMetric.objects.all().values(
        "channel", "period", "follower_growth", "reach", "views",
        "engagement_rate", "content_interactions", "ctr",
        "profile_visits", "link_clicks", "leads", "top_performing_post",
    ))
    return pd.DataFrame(rows)


def _number_sum(series):
    value = series.sum(min_count=1)
    return None if pd.isna(value) else float(value)


def _apply_filters(request, frame):
    channels = sorted(frame["channel"].dropna().unique().tolist()) if not frame.empty else []
    selected_channel = request.GET.get("channel", "All")
    if selected_channel not in channels:
        selected_channel = "All"
    selected_frame = frame.copy()
    if selected_channel != "All":
        selected_frame = selected_frame[selected_frame["channel"] == selected_channel]

    start_date = request.GET.get("start_date", "").strip()
    end_date = request.GET.get("end_date", "").strip()
    filter_error = ""
    if (start_date or end_date) and not selected_frame.empty:
        try:
            start = pd.to_datetime(start_date, errors="raise") if start_date else None
            end = pd.to_datetime(end_date, errors="raise") if end_date else None
            if start is not None and end is not None and start > end:
                raise ValueError
        except (ValueError, TypeError):
            start_date = end_date = ""
            filter_error = "The date range was invalid; date filters were not applied."
        else:
            parsed_periods = pd.to_datetime(selected_frame["period"], errors="coerce", format="mixed")
            valid_period = parsed_periods.notna()
            if start is not None:
                valid_period &= parsed_periods >= start
            if end is not None:
                valid_period &= parsed_periods <= end + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
            selected_frame = selected_frame[valid_period].copy()
            if parsed_periods.isna().any():
                filter_error = "Rows with non-date reporting periods are excluded while a date range is active."

    return channels, selected_channel, start_date, end_date, selected_frame, filter_error


def _aggregate_by_channel(frame, field, average=False):
    grouped = frame.groupby("channel")[field]
    values = grouped.mean() if average else grouped.agg(lambda series: series.sum(min_count=1))
    return [
        {"label": str(channel), "value": None if pd.isna(value) else float(value)}
        for channel, value in values.items()
    ]


def _canonical_period(period):
    text = str(period).strip()
    parsed = pd.to_datetime(text, errors="coerce", format="mixed")
    return parsed.date().isoformat() if pd.notna(parsed) else text


def dashboard(request):
    frame = _database_frame()
    channels, selected_channel, start_date, end_date, view_frame, filter_error = _apply_filters(request, frame)
    if view_frame.empty:
        kpis = {field: None for field in METRIC_FIELDS}
        insights = ["Import data to start seeing insights."]#
        chart_data = {}
        top_posts = []
    else:
        kpis = {
            field: (
                float(view_frame[field].mean())
                if field == "engagement_rate" and view_frame[field].notna().any()
                else _number_sum(view_frame[field])
            )
            for field in METRIC_FIELDS
        }
        insights = build_insights(view_frame)
        period_order = list(dict.fromkeys(view_frame["period"].astype(str).tolist()))
        chart_data = {
            "periods": period_order,
            "channels": sorted(view_frame["channel"].dropna().unique().tolist()),
            "views": [],
            "reachByChannel": _aggregate_by_channel(view_frame, "reach"),
            "engagementByChannel": _aggregate_by_channel(view_frame, "engagement_rate", average=True),
            "leadsByChannel": _aggregate_by_channel(view_frame, "leads"),
        }
        for channel in chart_data["channels"]:
            channel_rows = view_frame[view_frame["channel"] == channel]
            values = []
            for period in period_order:
                period_rows = channel_rows[channel_rows["period"].astype(str) == str(period)]
                values.append(_number_sum(period_rows["views"]) if not period_rows.empty else None)
            chart_data["views"].append({"label": channel, "data": values})
        top_posts = view_frame[
            view_frame["top_performing_post"].fillna("").astype(str).str.strip().ne("")
        ][["channel", "period", "top_performing_post", "views", "engagement_rate"]].to_dict("records")

    context = {
        "kpis": kpis,
        "channels": channels,
        "selected_channel": selected_channel,
        "start_date": start_date,
        "end_date": end_date,
        "filter_error": filter_error,
        "insights": insights,
        "chart_data": chart_data,
        "top_posts": top_posts[:10],
        "last_import": SocialMetric.objects.order_by("-imported_at").values_list("imported_at", flat=True).first(),
        "row_count": len(frame),
        "filtered_row_count": len(view_frame),
    }
    return render(request, "analytics/dashboard.html", context)


def channel_comparison(request):
    frame = _database_frame()
    channels, selected_channel, start_date, end_date, view_frame, filter_error = _apply_filters(request, frame)
    metrics = []
    for field in METRIC_FIELDS:
        if field == "engagement_rate":
            grouped = view_frame.groupby("channel")[field].mean() if not view_frame.empty else pd.Series(dtype=float)
        else:
            grouped = (
                view_frame.groupby("channel")[field].agg(lambda values: values.sum(min_count=1))
                if not view_frame.empty else pd.Series(dtype=float)
            )
        metrics.append({
            "key": field,
            "label": field.replace("_", " ").title(),
            "values": [
                {"channel": str(channel), "value": None if pd.isna(value) else float(value)}
                for channel, value in grouped.items()
            ],
        })
    context = {
        "channels": channels,
        "comparison_channels": sorted(view_frame["channel"].dropna().unique().tolist()) if not view_frame.empty else [],
        "selected_channel": selected_channel,
        "start_date": start_date,
        "end_date": end_date,
        "filter_error": filter_error,
        "metrics": metrics,
        "metrics": metrics,
        "row_count": len(view_frame),
    }
    return render(request, "analytics/comparison.html", context)


def insights_page(request):
    frame = _database_frame()
    channels, selected_channel, start_date, end_date, view_frame, filter_error = _apply_filters(request, frame)
    context = {
        "channels": channels,
        "selected_channel": selected_channel,
        "start_date": start_date,
        "end_date": end_date,
        "filter_error": filter_error,
        "insights": build_insights(view_frame),
        "period_changes": build_period_changes(view_frame),
        "period_series": build_period_series(view_frame),
        "row_count": len(view_frame),
        "top_posts": (
            view_frame[view_frame["top_performing_post"].fillna("").astype(str).str.strip().ne("")][
                ["channel", "period", "top_performing_post", "views", "engagement_rate"]
            ].to_dict("records")[:10]
            if not view_frame.empty else []
        ),
    }
    return render(request, "analytics/insights.html", context)


def _save_import(processed):
    existing = {
        (str(channel).strip(), _canonical_period(period))
        for channel, period in SocialMetric.objects.values_list("channel", "period")
    }
    seen = set()
    objects = []
    skipped = 0
    for row in processed.frame.itertuples(index=False):
        channel = str(row.channel)
        period = str(row.period)
        key = (channel, _canonical_period(period))
        if len(channel) > 100 or len(period) > 100:
            processed.rejected.append({
                "line": "—",
                "errors": ["Channel and Period must each be 100 characters or fewer"],
            })
            continue
        if key in existing or key in seen:
            skipped += 1
            continue
        seen.add(key)
        objects.append(SocialMetric(
            channel=channel,
            period=period,
            follower_growth=row.follower_growth,
            reach=row.reach,
            views=row.views,
            engagement_rate=row.engagement_rate,
            content_interactions=row.content_interactions,
            ctr=row.ctr,
            profile_visits=row.profile_visits,
            link_clicks=row.link_clicks,
            leads=row.leads,
            top_performing_post=row.top_performing_post or "",
        ))
    with transaction.atomic():
        SocialMetric.objects.bulk_create(objects)
    return {
        "imported": len(objects),
        "skipped": skipped,
        "rejected": len(processed.rejected),
        "total": processed.total_rows,
        "rejections": processed.rejected[:20],
        "more_rejections": max(0, len(processed.rejected) - 20),
        "warnings": processed.warnings,
    }


@require_http_methods(["GET", "POST"])
def import_sheet(request):
    result = None
    if request.method == "POST":
        try:
            upload = request.FILES.get("csv_file")
            shared_url = request.POST.get("sheet_url", "").strip()
            if upload:
                processed = process_csv_upload(upload)
            elif shared_url:
                processed = fetch_sheet_dataframe(shared_url)
            else:
                raise CsvImportError("Choose a CSV file or enter a Google Sheets URL.")
            result = _save_import(processed)
            if result["imported"]:
                messages.success(request, f"Import complete: {result['imported']} rows imported.")
            elif result["skipped"] and not result["rejected"]:
                messages.info(request, "Import complete: every valid row was already in the database.")
            elif result["rejected"]:
                messages.warning(request, "The file was processed, but no valid new rows were imported.")
        except (CsvImportError, SheetImportError) as exc:
            messages.error(request, str(exc))
        except Exception:
            logger.exception("Social metrics import failed")
            messages.error(request, "The import could not be completed. Check the file and try again.")
    return render(request, "analytics/import.html", {"result": result})
