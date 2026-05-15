# Instagram AI Sales Bot

Automated Instagram DM sales bot powered by Claude AI with anti-ban protection and a React monitoring dashboard.

## What it does

- Monitors Instagram DMs and responds with human-like delays using Claude AI
- Impersonates a live sales manager — never reveals it's a bot
- Tracks conversations through a sales funnel (new → in_progress → converted)
- Protects accounts with warmup schedules, random delays, and automatic pause on errors
- Dashboard for monitoring, pausing, and controlling the bot in real time

## Architecture

```
Instagram DMs → poll_account_dms (Celery, every 60-180 s)
                    ↓
              process_message (Celery, human delay 11-49 s)
                    ↓
              Claude API → send DM via instagrapi
                    ↓
              PostgreSQL (logs everything)
                    ↓
              React Dashboard (monitor + control)
```

## Prerequisites

- VPS with Ubuntu 22.04+ / Debian 12+
- Docker Engine + Docker Compose v2
- A secondary Instagram account for testing (never test on a primary account)
- Anthropic API key (get at console.anthropic.com)

## Quick Deploy

### 1. Clone and configure

```bash
git clone <repo-url> igbot && cd igbot
cp .env.example .env
```

Generate required keys:
```bash
# ENCRYPTION_KEY (Fernet key for session encryption)
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# SECRET_KEY (JWT secret)
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Edit `.env` and fill in:
- `ANTHROPIC_API_KEY` — from console.anthropic.com
- `ENCRYPTION_KEY` — generated above (44-char base64 string)
- `SECRET_KEY` — generated above
- `POSTGRES_PASSWORD` — choose a strong password (change the default)

### 2. Start infrastructure

```bash
docker compose up -d postgres redis
# Wait for postgres to be healthy
docker compose ps
```

### 3. Run database migration

```bash
docker compose run --rm backend alembic upgrade head
```

Expected: `INFO [alembic.runtime.migration] Running upgrade -> 001, Initial schema`

### 4. Start all services

```bash
docker compose up -d
docker compose ps
```

Expected: all 6 services running.

### 5. Verify the API

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

### 6. Open the dashboard

Navigate to `http://<your-vps-ip>:3000`

### 7. Add your first Instagram account

```bash
curl -X POST http://localhost:8000/api/accounts \
  -H "Content-Type: application/json" \
  -d '{
    "username": "your_ig_username",
    "password": "your_ig_password",
    "business_name": "Your Business Name",
    "service_description": "what you sell (e.g. nail art services)",
    "price_info": "starting from $X",
    "objections_script": "We offer flexible payment plans and a satisfaction guarantee"
  }'
```

The bot will start polling Instagram DMs within 90 seconds.

## Anti-ban Protection

| Protection | Detail |
|---|---|
| Human delays | Random 11–49 s before each reply |
| Typing simulation | Types for `len(text) × rand(0.05, 0.1)` seconds before sending |
| Warmup schedule | Day 1–3: 15/day → Day 4–7: 30/day → Day 8–14: 50/day → Day 15+: 80/day |
| Random poll interval | 90 s base + random 0–60 s jitter per account |
| Encrypted sessions | Instagram session stored with Fernet encryption — password never persisted |
| Auto-pause | ChallengeRequired or RateLimitError triggers error state + dashboard alert |
| Daily limit reset | Resets at system midnight (hourly check) |

## Dashboard

| Page | URL | Purpose |
|---|---|---|
| Dashboard | `/` | Bot status (ACTIVE/PAUSED/ERROR), daily usage, pause/resume |
| Conversations | `/conversations` | Full DM history, stage filter, human takeover |
| Stats | `/stats` | Sent/received charts, token usage, conversion funnel |
| Settings | `/settings` | Edit system prompt, limits, LLM model |

## API Reference

### Accounts
```
POST   /api/accounts              Add Instagram account + initial login
GET    /api/accounts              List all accounts
DELETE /api/accounts/{id}         Remove account
```

### Bot Control
```
POST   /api/bot/{id}/pause        Manually pause bot
POST   /api/bot/{id}/resume       Resume bot
GET    /api/bot/{id}/status       Current status + today's message count
GET    /api/bot/{id}/config       Current bot configuration
PUT    /api/bot/{id}/config       Update system prompt, limits, LLM model
```

### Conversations
```
GET    /api/conversations/{account_id}           List conversations (filter: ?stage=new|in_progress|converted|dead)
GET    /api/conversations/{account_id}/{thread}  Full conversation with message history
POST   /api/conversations/{thread}/takeover      Disable bot for this conversation (human takes over)
POST   /api/conversations/{thread}/restore       Re-enable bot for this conversation
```

### Stats
```
GET    /api/stats/{id}/daily?days=7    Daily stats for last N days (max 90)
GET    /api/stats/{id}/summary         All-time totals + conversion rate
```

## Common Operations

```bash
# View worker logs (message processing)
docker compose logs -f worker

# View beat logs (scheduling)
docker compose logs -f beat

# Restart workers after code changes
docker compose restart worker beat

# Stop everything
docker compose down

# Pull updates and redeploy
git pull
docker compose build
docker compose up -d

# Backup database
docker compose exec postgres pg_dump -U igbot igbot > backup_$(date +%Y%m%d).sql

# Restore database
docker compose exec -T postgres psql -U igbot igbot < backup.sql
```

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| Bot status = `error` | Instagram blocked or challenge required | Check `pause_reason` via `/api/bot/{id}/status`. Manually verify the account on Instagram app, then resume. |
| `ChallengeRequired` error | Instagram wants human verification | Log in to Instagram manually from same IP (or the account's usual IP). Wait 1–24 hours, then resume. |
| Messages not sending | Worker down | `docker compose logs worker` — check for exceptions. Restart: `docker compose restart worker`. |
| Database connection failed | Wrong `DATABASE_URL` | Verify env: `docker compose exec backend env \| grep DATABASE`. |
| Frontend not loading | Build issue or nginx misconfiguration | `docker compose logs frontend`. Rebuild: `docker compose build frontend && docker compose up -d frontend`. |
| High token costs | LLM model set to Sonnet | Switch to Haiku via Settings page or `PUT /api/bot/{id}/config` with `{"llm_model": "claude-haiku-3-5-20251001"}`. |

## Configuration Reference

All settings editable via `/api/bot/{id}/config` or the Settings page:

| Field | Default | Description |
|---|---|---|
| `business_name` | — | Business name used in system prompt |
| `service_description` | — | What you sell |
| `price_info` | — | Pricing details (shared only after dialogue) |
| `objections_script` | — | How to handle common objections |
| `llm_model` | `claude-haiku-3-5-20251001` | AI model (`claude-haiku-3-5-20251001` or `claude-sonnet-4-6`) |
| `max_messages_per_day` | `80` | Hard cap on daily outgoing messages |
| `min_delay_sec` | `8.0` | Minimum base delay before responding |
| `max_delay_sec` | `25.0` | Maximum base delay before responding |
| `warmup_mode` | `true` | Auto-limit by account age (recommended for new accounts) |

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11 + FastAPI |
| Instagram | instagrapi (unofficial, session-based) |
| LLM | Anthropic Claude API |
| Queue | Redis + Celery |
| Database | PostgreSQL 15 + SQLAlchemy |
| Dashboard | React 18 + Vite + TailwindCSS |
| Deployment | Docker Compose |

## Legal / Ethics

This tool uses an unofficial Instagram API and violates Instagram's Terms of Service. Use at your own risk on accounts you control. Always disclose to clients that you are using automation. The bot is designed to NOT reveal it is an AI — ensure this complies with applicable consumer protection laws in your jurisdiction.
