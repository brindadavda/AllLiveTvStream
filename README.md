# 🌊 HydraStream IPTV Intelligent Backend

HydraStream is a high-performance, stable, and intelligent streaming backend system for IPTV. It acts as an enriched IPTV middleware, parsing, validating, caching, and serving 360,000+ globally sourced channels from the official IPTV-org directory with sub-millisecond latencies.

## 🚀 Key Features

* **Dual-Mode Resilient Architecture**: Seamless fallback mechanism. Operates on a highly robust local File Mock DB & In-Memory Cache when offline, and automatically escalates to a production-grade MongoDB Atlas cloud database & Redis cache when online.
* **Rapid Ingest Engine**: Paralellized high-concurrency ingestion script that fetches all 13 official IPTV-org collections and bulk-upserts 360k+ items into MongoDB Atlas in under 6 minutes.
* **Lightning-Fast Caching Layer**: Fully cached API response routes (via Redis or fallback cache) resulting in query latencies of **< 2.0 milliseconds** for channels, categories, and countries!
* **Automated Stream Validation Workers**: Dynamic background workers (leveraging APScheduler & HTTPX-based async workers) that periodically check active stream URLs to measure connection latencies, verify HLS formats, parse stream resolutions, and filter out dead streams.
* **Complete Endpoint Suite**: Fully documented, standard JSON responses matching strict Pydantic schemas.

---

## 🛠 Tech Stack

* **Backend Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.9+)
* **Asynchronous DB Client**: [Motor (MongoDB Async Driver)](https://motor.readthedocs.io/)
* **Cache System**: [Redis](https://redis.io/) (with local memory fallback)
* **Background Scheduler**: [APScheduler](https://apscheduler.readthedocs.io/)
* **Model Validation**: [Pydantic v2](https://docs.pydantic.dev/)

---

## 📦 Project Structure

```text
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI routers and route handlers
│   │   ├── cache/        # Redis connection setup and caching hooks
│   │   ├── database/     # Async MongoDB client & File MockDB fallback
│   │   ├── models/       # MongoDB document mapping definitions
│   │   ├── schemas/      # Pydantic request and response schemas
│   │   ├── services/     # M3U Playlist downloading, parsing & enrichment
│   │   ├── utils/        # Structured logging modules
│   │   ├── validators/   # Async stream HLS validation helpers
│   │   └── workers/      # Periodical cron scheduler validation tasks
│   ├── data/             # Local offline JSON collections fallback
│   ├── main.py           # FastAPI entrypoint and startup/shutdown events
│   ├── requirements.txt  # Python requirements file
│   ├── vercel.json       # Ephemeral serverless configuration
│   └── tests/            # Test suites
│       └── test_unit.py  # Lifecycle-validated API integration tests
├── scripts/
│   ├── fetch_and_populate_all.py  # Master 13-collection cloud ingestion tool
│   ├── test_apis.py               # Active API routing verification script
│   └── performance_test.py        # Throughput stress testing engine
```

---

## ⚙️ Local Development Setup

### 1. Configure the Environment
Create a `.env` file in both the root directory and the `backend/` directory:

```env
APP_NAME="HydraStream Backend"
APP_ENV="development"

# MongoDB Database URI (Local or Atlas)
MONGO_URI="mongodb+srv://<username>:<password>@cluster0.mongodb.net/hydra_stream"
MONGO_DB="hydra_stream"

# Redis Server Connection
REDIS_URI="redis://localhost:6379"

# Playlist Configuration
PLAYLIST_URL="https://iptv-org.github.io/iptv/index.m3u"
PLAYLIST_REFETCH_HOURS=12
VALIDATION_INTERVAL_MINUTES=30
```

### 2. Ingest the Data
Ingest the 13 official IPTV-org collections directly into your MongoDB database:
```bash
python3 scripts/fetch_and_populate_all.py
```

### 3. Launch the Server
Start the Uvicorn ASGI server:
```bash
cd backend
python3 -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```
* **Interactive OpenAPI/Swagger UI**: `http://127.0.0.1:8000/docs`
* **Redoc UI alternative**: `http://127.0.0.1:8000/redoc`

---

## ⚡ API Endpoint Reference

| Method | Endpoint | Description | Cache Status |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | Service health status & exposed route index | Live |
| `GET` | `/api/v1/channels` | Paginated working streams (with optional country, language, category filters) | Cached (5 mins) |
| `GET` | `/api/v1/search` | Regex-based search matching name, categories, countries, and languages | Live |
| `GET` | `/api/v1/channel/{id}` | Detailed properties of a single stream + increment trending | Live |
| `GET` | `/api/v1/channels/fastest` | Active channels sorted by response latency ascending | Live |
| `GET` | `/api/v1/categories` | Distinct categories list + active channel counts | Cached (5 mins) |
| `GET` | `/api/v1/countries` | Distinct countries list + active channel counts | Cached (5 mins) |
| `GET` | `/api/v1/languages` | Distinct languages list + active channel counts | Cached (5 mins) |
| `GET` | `/api/v1/trending` | Top trending streams based on popularity scores | Cached |

---

## 🧪 Testing & Verification

Run the full local integration verification script to check endpoint latencies:
```bash
python3 scripts/test_apis.py
```

Run the unit testing suite to verify system assertions:
```bash
PYTHONPATH=backend python3 backend/tests/test_unit.py
```

---

## ☁️ Vercel Serverless Deployment Guide

Vercel is a highly robust serverless environment. To deploy this backend to Vercel:

### 1. Configuration Check
A pre-configured `vercel.json` file is located inside `/backend/vercel.json`. It specifies `@vercel/python` as the serverless builder and maps all requests directly to `main.py`.

### 2. Configure Project settings on Vercel
* Import your git repository.
* **CRITICAL**: Change your project's **Root Directory** inside Vercel's build settings to **`backend`**.
* Add your environment variables:
  * `MONGO_URI` (Cloud connection)
  * `MONGO_DB` (`hydra_stream`)
  * `REDIS_URI` (Vercel is serverless! Use a cloud Redis server like [Upstash Redis](https://upstash.com) instead of `localhost`)

### 3. ephemerality / Cron setup
In serverless platforms like Vercel, memory processes scale down to zero when idle, meaning local loops or persistent timers (`apscheduler`) will not run continuously.
* To keep streams updated, configure an external validation trigger at [cron-job.org](https://cron-job.org) or Upstash QStash to hit a verification trigger endpoint on a periodic schedule.
