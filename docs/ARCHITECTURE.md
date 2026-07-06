# System Architecture

## 1. High-level overview

Everything server-side runs on a single Azure `Standard_B1s` VM (1 vCPU, 1 GiB RAM).
The design goal on that budget: **the API process never does slow work.**
Anything that takes more than ~100 ms (PDF parsing, LLM calls, polling job
boards, Telegram delivery) is pushed through Redis to a separate worker process.

```
                 Vercel (free)                          Azure B1s VM (Ubuntu)
┌────────────────────────┐   HTTPS   ┌──────────────────────────────────────────────┐
│  React SPA (Vite)      │──────────▶│  nginx :443  (TLS, rate-limit, 10 MB cap)    │
│  - Kanban board        │           │     │                                        │
│  - Alerts feed         │           │     ▼                                        │
│  - Resume tailoring UI │           │  Uvicorn :8000 — FastAPI (async, 1 worker)   │
└────────────────────────┘           │     │ SQL (asyncpg)      │ enqueue (arq)     │
                                     │     ▼                    ▼                   │
┌────────────────────────┐  webhook  │  PostgreSQL 16    ═══ Redis (local) ═══      │
│  Telegram servers      │──────────▶│  (localhost)             │ dequeue           │
│  (bot API)             │◀──────────│                          ▼                   │
└────────────────────────┘  sendMsg  │  ARQ worker process (cron + task queue)      │
                                     │   ├─ fetch_and_notify (every 15 min)         │
┌────────────────────────┐           │   ├─ parse_resume (on upload)                │
│  Job boards (Remotive, │◀──────────│   └─ run_generation (tailor / cover letter)  │
│  Adzuna, ...)          │   HTTPS   │            │                                 │
└────────────────────────┘           │            ▼  HTTPS                          │
                                     │   Gemini API (gemini-3.1-flash-lite)         │
┌────────────────────────┐  channel  │                                              │
│  Discord channel       │◀──────────│   (fetch_and_notify also broadcasts every    │
│  (community jobs feed) │  webhook  │    new student job to Discord)               │
└────────────────────────┘           └──────────────────────────────────────────────┘
```

### Why the API thread never blocks

- **FastAPI is fully async.** Every DB call goes through SQLAlchemy 2.0 async +
  `asyncpg`; every outbound HTTP call uses `httpx.AsyncClient`. A single Uvicorn
  worker handles many concurrent requests because handlers yield at every await.
- **Slow work is enqueued, not executed.** `POST /ai/tailor` inserts an
  `ai_generations` row with `status='pending'`, pushes a job id to Redis via
  ARQ, and returns immediately (~10 ms). The frontend polls
  `GET /ai/generations/{id}` until `status='done'`.
- **The worker is a separate OS process** (`arq app.workers.settings.WorkerSettings`),
  so a 20-second Gemini call or a CPU-heavy PDF parse cannot stall an HTTP request.
  ARQ also owns the **cron schedule** — `fetch_and_notify` runs every 15 minutes
  inside the worker, so no separate "beat" process is needed (important on 1 GiB RAM).
- **Telegram is push, not poll.** Outbound alerts are plain HTTPS calls to
  `api.telegram.org` from the worker. Inbound (`/start <token>` account linking)
  arrives as a webhook that Telegram POSTs to nginx → FastAPI, verified by a
  secret header. No long-polling process to keep alive.

### Why ARQ and not Celery

Celery + its beat scheduler costs two extra processes and ~150 MB RSS — a lot on
a B1s. ARQ is a single asyncio process, speaks the same async idioms as FastAPI,
and has built-in cron. Redis itself runs locally on the VM (~10 MB idle):
managed free tiers bill per command, and a polling queue worker issues ~170K
commands a day just asking "any jobs?" — colocating the queue makes that free.

## 2. Core flows

### Flow A — Real-time job alert (two-lane fan-out)
1. Cron fires `fetch_and_notify` in the worker every hour.
2. The active source adapter fetches recent student postings. Primary source:
   **Bright Data's LinkedIn jobs dataset** (`job_sources/brightdata.py`) —
   keyword-discovery scrape ("student", Israel, past 24 h); the keyless
   Remotive adapter is the automatic fallback for local dev.
3. Jobs are upserted into `jobs`. Dedup key: LinkedIn's `job_posting_id` is
   stored as `external_id`, and `UNIQUE(source, external_id)` silently drops
   postings we've already seen — so nobody is ever notified twice.
4. **Lane 1 — Discord firehose:** *every* new job is posted to the community
   Discord channel via a channel webhook (`services/discord.py`). No bot
   process needed — it's one HTTPS POST. `jobs.discord_notified_at` marks
   success, so a failed webhook call is retried next cycle.
5. **Lane 2 — personal Telegram alerts:** new jobs are matched against every
   active `search_preferences` row (`services/matching.py` — the criteria each
   user defined in the web app). A match inserts `job_alerts`
   (`UNIQUE(user_id, job_id)` prevents double pings) and, if the user linked
   Telegram, sends a formatted message with an "Applied ✅" path back to the
   web app.

So: the Discord channel receives the full public feed of found student jobs,
while each user's Telegram only receives the jobs that fit *their* saved
criteria.

### Flow B — ATS Jailbreaker
1. `POST /resumes` (multipart PDF) → file saved to `uploads/{user_id}/`,
   `resumes` row inserted, `parse_resume` enqueued → **202 returned instantly**.
2. Worker extracts text (`pypdf`) and runs the simulated ATS parser
   (`services/ats_parser.py`): skills dictionary matching, section detection,
   contact extraction — the same crude logic real ATS filters use.
3. `POST /ai/tailor {resume_id, job_description}` → `ai_generations` row → queue.
4. Worker builds the gap-analysis prompt (`services/tailoring.py`), calls Gemini
   with `responseMimeType: application/json`, stores structured rewrites +
   before/after ATS scores in `result`.

### Flow C — Kanban
- `GET /applications` returns all cards; the frontend groups them into columns.
- Drag & drop calls `POST /applications/{id}/move {status, sort_order}`.
  `sort_order` is a float set to the midpoint between neighbours — an O(1)
  write, no renumbering. Every status change also appends to
  `application_events` (history/analytics).
- "Applied" on an alert calls `POST /applications/from-alert/{alert_id}`, which
  copies the job into a card in one transaction.

### Flow D — Telegram account linking
1. Web app shows `GET /telegram/link` → `https://t.me/<bot>?start=<uuid-token>`.
2. User taps it; Telegram sends `/start <token>` to the bot's webhook.
3. FastAPI resolves the token to a user, stores `telegram_chat_id`, replies
   "Linked ✅" in the chat. The token lives in `users.telegram_link_token`.

## 3. Backend module map

```
backend/app/
├── main.py               # app factory, lifespan (arq pool), CORS, routers
├── core/
│   ├── config.py         # pydantic-settings — single source of env config
│   ├── database.py       # async engine, session factory, Base, get_db dep
│   └── security.py       # bcrypt hashing, JWT create/decode
├── models/               # SQLAlchemy ORM — mirrors db/schema.sql exactly
├── schemas/              # Pydantic request/response contracts
├── api/
│   ├── deps.py           # get_current_user (JWT bearer), get_arq
│   └── routes/           # auth, preferences, jobs, applications, resumes, ai, telegram
├── services/             # business logic — no FastAPI imports, unit-testable
│   ├── llm.py            # thin async Gemini REST client
│   ├── ats_parser.py     # simulated ATS: pypdf text + skill/section extraction
│   ├── tailoring.py      # gap analysis + sentence rewriting prompts
│   ├── cover_letter.py   # cover letter / LinkedIn message prompts
│   ├── matching.py       # preference ↔ job keyword matching
│   ├── telegram.py       # sendMessage + deep-link helpers (personal alerts)
│   ├── discord.py        # channel-webhook broadcast (community jobs feed)
│   └── job_sources/      # adapter per job board (base protocol + remotive)
└── workers/
    ├── settings.py       # ARQ WorkerSettings: functions, cron, redis
    └── tasks.py          # parse_resume, run_generation, fetch_and_notify
```

**Layering rule:** `api/` may import `services/` and `models/`; `services/`
never imports `api/`. The worker reuses the exact same `services/` and
`models/` code — one implementation of business logic, two entry points.

## 4. Authentication

- Register/login with email + bcrypt-hashed password.
- Login returns a short-lived **access JWT** (30 min) and a long-lived
  **refresh JWT** (14 days) with a `type` claim so one can't be used as the other.
- Every protected route resolves the user via the `Authorization: Bearer` header
  (`api/deps.py`). Row ownership is enforced in every query
  (`WHERE user_id = current_user.id`) — never trust ids from the client.
- Stateless refresh keeps the schema simple; if you later need "log out
  everywhere", add a `token_version` column to `users` and stamp it into claims.

## 5. Scaling notes (for the project report)

- The single-VM design is deliberate (student tier). The seams are already in
  place to split it: the worker can move to a second VM unchanged (it only talks
  to Redis + Postgres), Postgres can move to a managed instance by changing
  `DATABASE_URL`, and the API is stateless so it can scale horizontally behind
  a load balancer.
- Matching is O(new_jobs × active_prefs) in Python. Past ~10k prefs, push it
  into Postgres full-text search (`to_tsvector` on jobs + GIN index).
