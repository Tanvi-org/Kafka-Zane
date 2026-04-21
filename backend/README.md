# Event-driven GitHub webhook POC (FastAPI · Kafka · Redis · PostgreSQL)

This folder is a **minimal proof of concept**: a GitHub-style webhook receives events, **does not** run heavy work inline, publishes to **Kafka**, and a **separate worker** resolves **tenant** (installation → tenant), uses **Redis** as a cache, **PostgreSQL** as source of truth, then runs **impact analysis** (stub).

---

## What problem this solves

| Before | After |
|--------|--------|
| `PR webhook → do impact analysis in the HTTP request` (slow, scales badly) | `webhook → enqueue → workers scale horizontally` |
| One failure mode for API + analysis | Webhook stays fast; retries/DLQ in the worker |

---

## Architecture (high level)

```mermaid
flowchart LR
  subgraph ingress
    GH[GitHub or Postman]
    API[FastAPI /webhook]
  end
  subgraph messaging
    K[Kafka topic github-events]
    DLQ[DLQ github-events-dlq]
  end
  subgraph workers
    C[Consumer worker]
    TR[TenantResolver]
    IA[Impact analysis]
  end
  subgraph data
    R[(Redis)]
    P[(PostgreSQL)]
  end

  GH --> API
  API -->|produce| K
  K --> C
  C --> TR
  TR --> R
  TR --> P
  C --> IA
  C -->|after permanent failure| DLQ
```

### Responsibilities

| Piece | Responsibility |
|-------|----------------|
| **FastAPI (`app/main.py`, `app/webhook/handler.py`)** | Verify webhook (optional in dev), parse JSON, log `installation_id` / `delivery_id`, **produce one message to Kafka**, return `200` JSON quickly. |
| **Kafka** | Durable buffer between HTTP and workers; multiple consumers can share load (same **consumer group**). |
| **Consumer (`app/kafka/consumer.py`)** | Poll messages, **idempotency** per GitHub delivery, **retry** with backoff, **DLQ** on permanent failure, call resolver + impact analysis. |
| **Tenant resolver (`app/services/tenant_resolver.py`)** | Map `installation_id` → `tenant_id`: **Redis first**, then **Postgres**, then write-through cache. |
| **Redis (`app/db/redis_client.py`)** | Cache `inst:{installation_id} → tenant_id`; **idempotency** keys `idemp:delivery:{delivery_id}`. |
| **Postgres (`app/db/postgres.py`, `scripts/init_db.sql`)** | Table `github_installations` is the **authority** for installation → tenant. |
| **Impact analysis (`app/services/impact_analysis.py`)** | Your business logic; must use `tenant_id` for isolation (replace the stub). |

---

## Repository layout

```
backend/
├── app/
│   ├── main.py                 # FastAPI app, lifespan: Kafka producer + Redis for API
│   ├── config.py               # Env-driven settings (pydantic-settings)
│   ├── webhook/
│   │   └── handler.py          # POST /webhook
│   ├── kafka/
│   │   ├── producer.py         # Kafka producer (used by API + DLQ sends in worker)
│   │   └── consumer.py         # Worker entrypoint
│   ├── services/
│   │   ├── tenant_resolver.py
│   │   └── impact_analysis.py
│   ├── db/
│   │   ├── postgres.py
│   │   └── redis_client.py
│   ├── models/                 # Optional: ORM models later
│   └── utils/                  # Optional: shared helpers
├── scripts/
│   ├── init_db.sql             # Schema + seed row (runs on first Postgres init)
│   └── sample_pr_event.json    # Minimal body for Postman (matches seed installation_id)
├── docker-compose.yml          # ZooKeeper + Kafka + Redis + Postgres
├── requirements.txt
├── .env.example
└── README.md                   # This file
```

---

## Configuration (environment)

Copy `.env.example` to `.env` and adjust.

| Variable | Purpose |
|----------|---------|
| `GITHUB_WEBHOOK_SECRET` | Secret from the GitHub App webhook settings; used for HMAC SHA-256 (`X-Hub-Signature-256`). |
| `VERIFY_GITHUB_SIGNATURE` | `true` in production. Set `false` **only** for local tests without signing. |
| `KAFKA_BOOTSTRAP_SERVERS` | Broker address (`localhost:9092` with this compose). |
| `KAFKA_TOPIC_GITHUB` | Main topic (default `github-events`). |
| `KAFKA_TOPIC_DLQ` | Dead-letter topic (default `github-events-dlq`). |
| `KAFKA_GROUP_ID` | Consumer group id for workers. |
| `REDIS_URL` | Redis connection URL. |
| `DATABASE_URL` | AsyncPG URL: `postgresql://app:app@localhost:5432/app` matches compose. |

---

## How to run locally

### 1. Start infrastructure

From `backend/`:

```bash
docker compose up -d
```

This starts **ZooKeeper**, **Kafka**, **Redis**, and **Postgres**. The first time Postgres starts, it runs `scripts/init_db.sql` (schema + seed installation `12345678` → tenant `aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee`).

**Note:** If you already had an old Postgres volume, the init script will **not** re-run. Remove the volume or run the SQL manually (see Troubleshooting).

### 2. Python environment

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env
# Edit .env: set GITHUB_WEBHOOK_SECRET to match Postman/GitHub
```

### 3. Run the API (terminal 1)

```bash
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Run the worker (terminal 2)

```bash
cd backend
.venv\Scripts\activate
python -m app.kafka.consumer
```

You should see logs: `consumer_started`, then idle until messages arrive.

---

## How to test the webhook without GitHub

### Option A: Signature verification off (quickest)

In `.env`:

```env
VERIFY_GITHUB_SIGNATURE=false
```

Send **POST** `http://localhost:8000/webhook` with body from `scripts/sample_pr_event.json` and header `Content-Type: application/json`. Optionally set `X-GitHub-Event: pull_request` and `X-GitHub-Delivery: test-delivery-1` (delivery id is used for idempotency and logging).

### Option B: With signature (closer to production)

GitHub computes:

`X-Hub-Signature-256: sha256=<HMAC_SHA256_HEX(body, secret)>`

Use a small script or Postman pre-request script to set the header from your `GITHUB_WEBHOOK_SECRET` and raw body bytes.

---

## End-to-end flow (step by step)

1. **HTTP** hits `POST /webhook`.
2. **Handler** parses JSON, extracts `installation_id` from `installation.id`, `pr_number` from `pull_request.number`, logs identifiers.
3. **Producer** sends a JSON **envelope** to topic `github-events` (key = `installation_id:pr_number`).
4. **API** returns **HTTP 202** `{"status":"accepted"}` — keep this fast; no impact analysis here.
5. **Consumer** reads the message (same schema).
6. **Idempotency:** if `X-GitHub-Delivery` was present and Redis already has `idemp:delivery:{delivery_id}`, skip (already processed successfully).
7. **TenantResolver:** Redis `inst:{installation_id}`; miss → Postgres `github_installations`; on hit, **set Redis** with TTL.
8. **Impact analysis** runs with `tenant_id` and full `payload` (stub logs PR title).
9. **Mark processed** in Redis for that `delivery_id` after success.
10. On repeated failures after retries, message payload is sent to **DLQ** topic `github-events-dlq` with `dlq_error` field, then offset is committed (adjust policy for production).

---

## Integrating your real GitHub App

1. **Deploy** this API behind HTTPS (same requirement as any GitHub webhook).
2. Set **Webhook URL** to `https://<your-host>/webhook` (no trailing slash required for this router; router is mounted at `/webhook` so path is `/webhook`).
3. Set **Webhook secret** = `GITHUB_WEBHOOK_SECRET` in `.env`.
4. Ensure **`installation_id` → `tenant_id`** exists in Postgres (and optionally pre-warm Redis). Your provisioning flow (on GitHub `installation` events) should insert/update `github_installations`.
5. Replace **`run_impact_analysis`** with your existing logic; pass `tenant_id` into every DB/API call that must be isolated per customer.
6. Scale **workers** by running more `python -m app.kafka.consumer` processes **with the same `KAFKA_GROUP_ID`** on multiple machines; Kafka distributes partitions across the group.

---

## Kafka topics

- **`github-events`**: created automatically on first produce (broker default `auto.create.topics.enable=true`) for local dev. For production, create topics explicitly with desired partition count and retention.
- **`github-events-dlq`**: same; failed messages after retries are produced here by the worker.

Optional: inspect messages with Conduktor, `kcat`, or Kafka console tools against `localhost:9092`.

---

## Operational notes (production-minded)

- **Webhook latency:** keep handler under ~2s: only verify + JSON parse + produce (this POC does exactly that).
- **Payload size:** very large payloads can hurt Kafka and logs; consider storing blobs elsewhere and passing a reference in the envelope.
- **Idempotency:** uses GitHub’s `X-GitHub-Delivery` when present. If missing (manual tests), duplicate processing is possible—fine for POC.
- **DLQ:** this POC **commits** the offset after DLQ send so the consumer does not stall; tune whether you want to **pause** failed messages instead.
- **Security:** never disable signature verification in production; use TLS for Redis/Postgres in real deployments.

---

## Troubleshooting

| Symptom | What to check |
|--------|----------------|
| `tenant_not_found` | Seed row installation id must match payload `installation.id` (see `scripts/init_db.sql`). |
| Postgres empty / no seed | First-time volume only runs init SQL. Run `init_db.sql` manually or `docker compose down -v` (destroys data). |
| Consumer cannot connect to Kafka | `KAFKA_ADVERTISED_LISTENERS` is `localhost:9092` for clients on the host. If you run the app **inside** Docker, use service name `kafka:9092` and adjust advertised listeners (advanced). |
| Signature errors | `VERIFY_GITHUB_SIGNATURE=true` and correct secret; or temporarily `false` for local JSON tests. |

---

## Next steps (beyond POC)

- Structured logging (JSON) and metrics (Prometheus).
- Separate **installation** webhook service updating `github_installations`.
- Vault / KMS for per-tenant secrets inside `run_impact_analysis`.
- Schema registry for Kafka message versions (`schema_version` is already in the envelope for forward compatibility).
