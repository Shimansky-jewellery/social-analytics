import pandas as pd


def _channel_totals(frame, field):
    grouped = frame.groupby("channel")[field].agg(lambda values: values.sum(min_count=1))
    return grouped.dropna()

#this show the highest channel metrics
def build_insights(frame: pd.DataFrame):
    if frame.empty:
        return ["Import data to see insights."]

    insights = []
    for field, label in (("views", "views"), ("reach", "reach"), ("leads", "leads")):
        totals = _channel_totals(frame, field)
        if len(totals) >= 2 and (totals == totals.max()).sum() == 1:
            best_channel = totals.idxmax()
            insights.append(
                f"{best_channel} had the highest reported {label} "# loop through the channel get views,reach,leads 
                f"({totals.loc[best_channel]:,.0f})."
            )

    engagement = frame.groupby("channel")["engagement_rate"].mean().dropna()
    if len(engagement) >= 2 and (engagement == engagement.max()).sum() == 1:
        best_channel = engagement.idxmax()
        insights.append(
            f"{best_channel} had the highest average reported engagement rate "
            f"({engagement.loc[best_channel]:.2f}%)."
        )

    if not insights:
        insights.append("There is not enough comparable populated data to identify a strongest channel.")
    return insights


def build_period_changes(frame: pd.DataFrame):
    if frame.empty:
        return []
    period_dates = pd.to_datetime(frame["period"], errors="coerce", format="mixed")
    if period_dates.isna().any():
        return []

    data = frame.copy()
    data["period_date"] = period_dates.dt.date
    period_totals = data.groupby("period_date", as_index=False).agg(
        follower_growth=("follower_growth", lambda values: values.sum(min_count=1)),
        views=("views", lambda values: values.sum(min_count=1)),
    ).sort_values("period_date")
    if len(period_totals) < 2:
        return []

    changes = []
    for metric, label in (("follower_growth", "follower growth"), ("views", "views")):
        previous = period_totals.iloc[-2][metric]
        latest = period_totals.iloc[-1][metric]
        if pd.isna(previous) or pd.isna(latest) or previous == 0:
            continue
        change_percent = (latest - previous) / abs(previous) * 100
        if abs(change_percent) >= 20:
            direction = "increased" if change_percent > 0 else "decreased"
            changes.append(
                f"Total {label} {direction} by {abs(change_percent):.1f}% "
                f"from {period_totals.iloc[-2]['period_date']} to {period_totals.iloc[-1]['period_date']}."
            )
    return changes


def build_period_series(frame: pd.DataFrame):
    if frame.empty:
        return None
    period_dates = pd.to_datetime(frame["period"], errors="coerce", format="mixed")
    if period_dates.isna().any():
        return None
    data = frame.copy()
    data["period_date"] = period_dates.dt.date
    totals = data.groupby("period_date", as_index=False).agg(
        follower_growth=("follower_growth", lambda values: values.sum(min_count=1)),
        views=("views", lambda values: values.sum(min_count=1)),
    ).sort_values("period_date")
    if len(totals) < 2 or totals["follower_growth"].notna().sum() < 2:
        return None
    return {
        "periods": [period.isoformat() for period in totals["period_date"]],
        "follower_growth": [
            None if pd.isna(value) else float(value) for value in totals["follower_growth"]
        ],
        "views": [None if pd.isna(value) else float(value) for value in totals["views"]],
    }
