# Web Analysis — SEO Checker

A Django-based technical SEO auditing tool. Paste any URL and get a scored report across 6 categories, with optional AI-powered insights and Google PageSpeed data.

---

## Features

- **Technical SEO audit** across 6 weighted categories (overall score 0–100)
- **AI Insights** — GPT-5.3 analyses page content and suggests improvements
- **PageSpeed Integration** — real Lighthouse scores and Core Web Vitals via Google PSI API
- **Single-page frontend** — no framework, no build step, works out of the box
- **Async processing** — Celery + Redis so the browser polls for results without blocking
- **Rate limiting** — 10 checks/hour per IP via DRF `ScopedRateThrottle`

### SEO Categories

| Category | Weight | What's checked |
|---|---|---|
| 🏷️ Meta Information | 25% | Title, meta description, canonical, robots, lang, viewport, OG tags, Twitter Card |
| 📄 Page Quality | 25% | H1/H2, word count, alt text, text-to-HTML ratio, heading hierarchy |
| 🔗 Page Structure | 20% | URL cleanliness, internal/external links, empty anchors |
| ⚙️ Server Configuration | 20% | HTTPS, status code, response time, redirects, robots.txt, sitemap, HSTS |
| 📊 External Signals | 10% | JSON-LD schema, OG completeness, Twitter Card, favicon |
| ⚡ Performance | advisory | Lighthouse scores, Core Web Vitals (LCP, CLS, FCP, TBT, TTI), CrUX real-user data |
| ✨ AI Insights | advisory | GPT-5.3 executive summary, content score, suggested title/meta, top recommendations |

---

## Stack

- **Backend** — Django 5.0.6 + Django REST Framework 3.15.2
- **Task queue** — Celery 5.4.0 + Redis
- **HTML parsing** — BeautifulSoup4 + lxml
- **HTTP client** — httpx (with SSRF protection)
- **AI** — OpenAI GPT-5.3
- **Performance data** — Google PageSpeed Insights API v5
- **Database** — SQLite (dev) / PostgreSQL (prod)

---

## Quick Start

### Prerequisites

- Python 3.11+
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (for Redis)
- Git

### 1. Clone & create virtual environment

```powershell
git clone <your-repo-url>
cd web-analysis
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt --only-binary :all:
```

### 2. Configure environment

```powershell
Copy-Item .env.example .env
```

Edit `.env` and fill in your keys:

```dotenv
DJANGO_SECRET_KEY=<generate with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">

# Required for AI insights
OPENAI_API_KEY=sk-...

# Required for PageSpeed / Core Web Vitals
GOOGLE_PAGESPEED_API_KEY=AIza...
```

### 3. Run migrations

```powershell
python manage.py migrate
```

### 4. Start all services

```powershell
.\start.ps1
```

This starts:
- Redis (Docker container `redis-dev` on port 6379)
- Django dev server on `http://127.0.0.1:8080`
- Celery worker (`--pool=solo`, queue: `seo_checks`)

### 5. Open the app

```
http://127.0.0.1:8080
```

### Stop all services

```powershell
.\stop.ps1
```

---

## API

### `POST /api/seo-check/`

Submit a URL for analysis.

**Request**
```json
{ "url": "https://example.com" }
```

**Response** `202 Accepted`
```json
{
  "id": "uuid",
  "url": "https://example.com",
  "status": "pending",
  "overall_score": null
}
```

### `GET /api/seo-check/<id>/`

Poll for results.

**Response** `200 OK` (when complete)
```json
{
  "id": "uuid",
  "url": "https://example.com",
  "final_url": "https://example.com/",
  "status": "done",
  "overall_score": 84,
  "ai_summary": "...",
  "ai_suggestions": { ... },
  "categories": [
    {
      "category": "meta",
      "display_name": "Meta Information",
      "score": 91,
      "weight": 0.25,
      "checks": [ ... ]
    }
  ]
}
```

---

## Project Structure

```
web-analysis/
├── apps/
│   └── seo_checker/
│       ├── analyzers/
│       │   ├── base.py            # Shared Check / CategoryResult dataclasses
│       │   ├── meta.py            # Meta tags analyzer
│       │   ├── page_quality.py    # Content quality analyzer
│       │   ├── page_structure.py  # URL & links analyzer
│       │   ├── server.py          # HTTP / server analyzer
│       │   ├── external_signals.py# Schema & social signals analyzer
│       │   ├── performance.py     # Google PageSpeed Insights analyzer
│       │   └── ai_insights.py     # GPT-5.3 content analyzer
│       ├── models.py              # SeoCheck, CheckCategory models
│       ├── serializers.py         # DRF serializers
│       ├── tasks.py               # Celery task orchestrating all analyzers
│       ├── views.py               # DRF API views (create + poll)
│       └── urls.py
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── celery.py
│   ├── urls.py
│   └── wsgi.py
├── templates/
│   └── seo_checker/
│       └── index.html             # Single-page frontend (vanilla JS)
├── manage.py
├── requirements.txt
├── start.ps1                      # Start Redis + Django + Celery
├── stop.ps1                       # Stop all services
└── .env.example
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DJANGO_SECRET_KEY` | ✅ | Django secret key |
| `DJANGO_SETTINGS_MODULE` | ✅ | e.g. `config.settings.development` |
| `DATABASE_URL` | ✅ | e.g. `sqlite:///db.sqlite3` |
| `REDIS_URL` | ✅ | e.g. `redis://localhost:6379/0` |
| `OPENAI_API_KEY` | optional | Enables AI insights (GPT-5.3) |
| `GOOGLE_PAGESPEED_API_KEY` | optional | Enables PageSpeed / Core Web Vitals |
| `ALLOWED_HOSTS` | ✅ | Comma-separated, e.g. `localhost,127.0.0.1` |

---

## Security Notes

- SSRF protection on all outbound HTTP requests — private/link-local IPs are blocked
- All secrets loaded via `django-environ` — never hardcoded
- Rate limiting: 10 SEO checks per hour per IP
- XSS protection: all dynamic HTML in the frontend is escaped

---

## Windows Notes

- Celery requires `--pool=solo` on Windows (prefork uses shared semaphores that Windows restricts)
- Redis runs via Docker — `start.ps1` handles creating/restarting the container automatically
- Use `;` instead of `&&` to chain commands in PowerShell
