# Business Directory Scraper

Django lead finder for dynamic business searches such as `Hospitals in Lagos with HMO`.

## Features

- AI-planned Google Places searches with up to 3 result pages per query variant.
- Saved search campaigns and deduped leads.
- Lead scoring for phone, website, email, reviews, and HMO signals.
- CSV, Excel XLSX, and JSON exports.
- Filters for keyword, missing website, phone, email, and duplicates.
- Selected-lead exports, lead notes, qualification flags, and duplicate detection.
- Always-on AI search planner for expanding natural-language prompts into focused query variants.

## Setup

Install dependencies:

```powershell
pip install -r requirements.txt
```

Set environment variables before running the app:

```powershell
$env:GOOGLE_API_KEY="your-google-api-key"
$env:GOOGLE_MAPS_API_KEY="your-google-api-key"
```

AI search planning:

```powershell
$env:OPENAI_API_KEY="your-openai-api-key"
$env:OPENAI_MODEL="gpt-4o-mini"
$env:OPENAI_SEARCH_VARIANTS="25"
$env:GOOGLE_SEARCH_WORKERS="8"
```

Google Places exposes up to 3 pages per individual query. Use Search depth / `OPENAI_SEARCH_VARIANTS` to broaden searches with more AI-generated query variants.

Run the app:

```powershell
python manage.py runserver
```

## Docker

Build the image:

```powershell
docker build -t business-directory-scraper .
```

Run with your `.env` file:

```powershell
docker run --env-file .env -p 8000:8000 business-directory-scraper
```

For persistent SQLite data, mount a volume or bind the database file:

```powershell
docker run --env-file .env -p 8000:8000 -v ${PWD}/db.sqlite3:/app/db.sqlite3 business-directory-scraper
```

For production, set `DJANGO_DEBUG=False`, configure `DJANGO_ALLOWED_HOSTS`, and prefer Postgres over SQLite if multiple instances will run.
