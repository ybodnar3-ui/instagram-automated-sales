# Instagram Automated Sales Bot — Project Context

## Що це за проєкт

SaaS-продукт для автоматизованих продажів через Instagram Direct.
- Бот моніторить вхідні повідомлення, відповідає через LLM (Claude Haiku)
- Відправляє outbound DM по списку цільових акаунтів
- React дашборд для управління акаунтами, налаштуваннями, статистикою

## Архітектура

```
backend/   — FastAPI + Celery + PostgreSQL + Redis
frontend/  — React + Vite + nginx
```

**Backend стек:**
- FastAPI (REST API)
- Celery + Celery Beat (фонові задачі: poll inbox кожні 90 сек)
- PostgreSQL (основна БД)
- Redis (Celery broker + результати)
- Playwright (headless Chromium для Instagram автоматизації)
- Claude Haiku API (LLM для відповідей)

**Instagram автоматизація:**
- `backend/services/instagram.py` — повністю переписано з instagrapi на **Playwright**
- Логін через headless Chromium (обходить detection краще ніж API)
- Сесія зберігається через `context.storage_state()` → Fernet-шифрування → PostgreSQL
- Proxy підтримка: JSON формат `{"server":"...","username":"...","password":"..."}`
- Duck-typing: `PlaywrightSession.get_settings()` сумісний зі старими callers

## Railway Deployment (LIVE)

| Сервіс | URL | Статус |
|--------|-----|--------|
| Backend | https://backend-production-c0daf.up.railway.app | ✅ LIVE |
| Frontend | https://frontend-production-8e462.up.railway.app | ✅ LIVE |

**Railway Project ID:** `2e8d491f-72b4-4f03-8454-47f043c56a96`
**Railway Token:** `376f45bc-229f-412c-a9bf-f85d22dee738`

**Backend service ID:** `e8c0b4d7-4db3-44a6-b910-7c4227de0489`
**Frontend service ID:** `10a837fa-29af-4bae-bb24-cdec5d25451b`

### Як деплоїти

```bash
# Backend
cd backend && railway service backend && railway up --detach

# Frontend
cd frontend && railway up --detach
```

### Ключові особливості Dockerfile (backend)

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy
ENV PYTHONPATH=/app \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
```

- **НЕ** `python:3.11-slim` — там немає Chromium
- `PYTHONPATH=/app` — потрібен щоб Celery ForkPoolWorker знаходив модулі
- `start.sh` використовує `python -m alembic`, `python -m celery`, `python -m uvicorn` (не голі бінарники — Playwright image має Python path конфлікти)

## Локальна розробка

```bash
# Backend (з окремого терміналу)
cd backend
source venv/bin/activate
uvicorn main:app --reload --port 8000

# Celery (окремий термінал)
cd backend
source venv/bin/activate
PYTHONPATH=$(pwd) python -m celery -A workers.celery_app worker --beat --loglevel=info -c 1
```

**Важливо:** Локальний `.env` використовує `REDIS_URL` з `/1` (database index 1):
```
...autorack.proxy.rlwy.net:48506/1
```
Щоб не конфліктувати з Railway Celery Beat який на `/0`.

## Поточні проблеми / Наступні кроки

### 1. Instagram Login через Railway IP — ОСНОВНА ПРОБЛЕМА
Railway працює на AWS datacenter IPs. Instagram блокує логін з datacenter.

**Рішення:** Residential proxy при першому логіні.
- Proxy формат у settings: `{"server":"http://ip:port","username":"user","password":"pass"}`
- Перевірений формат: IPRoyal, Webshare, BrightData (дешевий $4 proxy вже використали — IP був вже в blacklist)
- Після першого успішного логіну сесія зберігається в БД і proxy вже не потрібен для polling

### 2. Тестування з реальним Instagram акаунтом
- Потрібен тестовий Instagram акаунт
- Потрібен residential proxy для першого логіну
- Перевірити весь flow: логін → poll inbox → відповідь через LLM → outbound DM

### 3. Dashboard API Key
Дашборд захищений API ключем. Дефолтний: `VibeSales2026!`
Можна змінити в Railway env vars: `DASHBOARD_API_KEY`

### 4. Продуктова монетизація (TODO)
- Multi-tenant: зараз всі акаунти в одній БД без ізоляції між клієнтами
- Billing: немає обмежень по кількості акаунтів / повідомлень
- Onboarding: немає wizard для додавання першого акаунта

## Структура БД (ключові таблиці)

```
accounts          — Instagram акаунти (username, encrypted_session, proxy_url)
bot_config        — налаштування LLM per account (system_prompt, llm_model, limits)
conversations     — треди розмов
messages          — окремі повідомлення
daily_stats       — статистика per account per day
outbound_targets  — список акаунтів для outbound DM
triggers          — умовні тригери для автоматичних дій
```

**LLM модель дефолт:** `claude-haiku-4-5-20251001` (не `claude-haiku-3-5-*` — той не існує)

## Файли які змінювались останні

- `backend/services/instagram.py` — ПОВНІСТЮ ПЕРЕПИСАНО на Playwright
- `backend/requirements.txt` — замінено `instagrapi` на `playwright==1.45.0`
- `backend/Dockerfile` — Playwright base image
- `backend/start.sh` — `python -m` для всіх команд
- `backend/models/stats.py` — виправлено назву LLM моделі
- `frontend/Dockerfile` — додано `ARG VITE_API_URL`, `ENV`, `CMD`
- `frontend/nginx.conf` — `connect-src *` (замість `'self'`) для cross-origin API
- `frontend/.railwayignore` — виключення непотрібних файлів

## Як перевірити що всe живе

```bash
curl https://backend-production-c0daf.up.railway.app/health
# → {"status":"ok","db":"ok"}
```

Frontend: https://frontend-production-8e462.up.railway.app
