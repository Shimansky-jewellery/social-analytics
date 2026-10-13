# Social Media Insights Dashboard (Django)

A Django application that imports social media metrics from a CSV export or a publicly accessible Google Sheet, analyses the data with pandas, and visualises it with Chart.js.

## CSV upload

CSV is the primary import method:
1. In Google Sheets, choose **File → Download → Comma Separated Values (.csv)**.
2. In the app, choose **Upload CSV File**, select the downloaded `.csv` file, then click **Import and Analyse Data**.
3. Review imported, skipped, and rejected row counts and follow the dashboard link.

Uploads are limited to 8 MB. `Channel` and `Period` are required; recognized metric columns may be blank or omitted. Populated unsupported columns cause validation to stop so their data is not silently discarded. Bad rows are reported and excluded while valid rows are imported. Blank metric cells are stored as missing values, not zero. Recognized date periods are normalized to `YYYY-MM-DD`.

The database identifies a record by `(Channel, Period)`. Existing records and repeated keys later in the same upload are skipped; existing data is never deleted or overwritten. Upload a new reporting period to add data. Engagement and CTR values are stored in percentage points (for example `5.4%` is stored as `5.4`; a fraction such as `0.054` remains `0.054`).

The insights page compares the two latest parseable reporting dates and flags changes of 20% or more. If dates cannot be parsed or fewer than two periods are available, no period-change conclusion is shown.

## Google Sheets URL import

The sheet must be accessible without signing in, or be published to the web. A normal private Google sharing link cannot be read by this simple link importer without Google OAuth/API credentials.

1. Open the Google Sheet.
2. Choose **File → Share → Publish to web** (or ensure access is set to anyone with the link as Viewer).
3. Copy the spreadsheet URL and use the secondary URL import option in the app.

The importer converts standard Google Sheets links to a CSV export URL. It accepts a spreadsheet URL with a `gid` tab identifier and only `docs.google.com/spreadsheets` links to reduce SSRF risk.

## Run locally

Requires Python 3.10+.

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
# If .env does not exist yet: cp .env.example .env
# Put a private DJANGO_SECRET_KEY in .env. The real .env file is ignored by Git.
python manage.py migrate
python manage.py runserver

Open http://127.0.0.1:8000/

When `DATABASE_URL` is blank, local development uses `db.sqlite3`. To use PostgreSQL locally, put its connection URL in `DATABASE_URL` in `.env`.

## Vercel environment variables

Do not upload or commit `.env`. Vercel does not use this local file as deployment configuration; add the variables below in **Project → Settings → Environment Variables** for each environment (Production, Preview, and Development as needed):

| Variable | Value |
| --- | --- |
| `DJANGO_SECRET_KEY` | A unique, random Django secret key. Keep it private. |
| `DJANGO_DEBUG` | `0` |
| `DJANGO_ALLOWED_HOSTS` | Your production hostname(s), comma-separated, without `https://`. Vercel's `VERCEL_URL` is also accepted automatically. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Your public origin(s), comma-separated and including scheme, for example `https://your-domain.com`. Vercel preview origins are allowed automatically. |
| `DATABASE_URL` | The connection URL for a persistent PostgreSQL database from your database provider. |

The app reads `.env` locally and reads Vercel's injected environment variables when deployed. On Vercel, it requires `DATABASE_URL` and will fail clearly if it is missing; SQLite is not used because Vercel's function filesystem is ephemeral. A PostgreSQL driver and URL parser are included in `requirements.txt`, and production database connections require SSL.

After adding the production `DATABASE_URL`, apply migrations once against that database from a trusted local environment with the same URL in `.env`:

```bash
python manage.py migrate
```

Configure Vercel to serve the Django project using `config.wsgi:application`. Database provisioning and deployment configuration remain in the PostgreSQL provider and Vercel project; this repository contains no database credentials.

## Expected columns

- Channel (required)
- Period (required)
- Follower Growth
- Reach
- Views
- Engagement Rate (%)
- Content Interactions
- Click-Through Rate (CTR) (%)
- Profile Visits
- Link Clicks
- DMs/Leads Generated
- Top Performing Post

Headers are matched case-insensitively and tolerate extra spaces and common variants. The recommended structure has one row per channel per reporting period.

## Features

- CSV file upload and manual import from a Google Sheets link
- Summary KPI cards, channel/date filtering, and Chart.js graphs
- Channel comparison and data-based insights
- Imported data saved to local SQLite or a configured persistent PostgreSQL database
- CSRF protection, URL validation, response timeout, and upload/download size caps

## Notes

- Chart.js is loaded from a CDN, so the dashboard needs internet access to load charts.
- KPI totals across channels may double-count people if the same audience is reached on multiple platforms.
- Before public deployment, configure `DEBUG=False`, a secure `SECRET_KEY`, `ALLOWED_HOSTS`, HTTPS, and production static-file hosting.
