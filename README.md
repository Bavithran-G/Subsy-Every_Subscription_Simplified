# Subsy — Every Subscription, Simplified.

**Subsy** is a subscription management system built for the ODOO Cochin Hackathon problem statement
*Subscription Management System*. It runs the whole life of a subscription business for the fictional
**Brightloop Software**: products and plans → quotations → subscriptions → automatic recurring invoices →
payments → revenue reporting, with a self-service portal for customers

> One business event updates every downstream record. When a subscription falls due, the billing engine
> creates exactly one invoice for that period — with prices, taxes and discounts applied by rule — records the
> billing event, and makes the invoice available to the customer. Running it again never bills twice.

---

## Features

| Area | What it does |
|---|---|
| **Authentication** | Registration with unique email (DB-enforced, case-insensitive) and the PS password rules (>8 chars, upper, lower, special). bcrypt hashing, JWT sessions revocable on logout/password change, expiring single-use reset tokens (only the SHA-256 hash is stored). |
| **Roles** | **Admin** (everything; only role that can add staff, discounts, taxes, products, plans) · **Internal staff** (customers, quotations, subscriptions, invoices, payments) · **Customer** (own records only, via the portal). Enforced server-side on every endpoint; customers get `404` for others' records. |
| **Products & variants** | Name, type, sales/cost price, notes, tax, archive. Configurable variants with price adjustments (e.g. *Brand: Odoo +₹560*); duplicate combinations rejected. |
| **Plans** | Daily / weekly / monthly / yearly (with intervals), minimum quantity, availability window, term length, and per-plan switches: auto-close, early close, pause, renew. |
| **Quotations** | Templates with plan, product lines, validity and payment terms. Draft → sent → confirmed; expired quotations cannot be confirmed until extended. Confirmed quotations are locked. |
| **Subscriptions** | Controlled lifecycle **Draft → Quotation → Confirmed → Active → Closed** (+ Paused, Cancelled). Every transition validated and recorded with user, time and reason. Pause/resume, renewal (once per term, DB-enforced), early and automatic closure — all subject to plan rules. |
| **Recurring billing** | Scheduled engine (daily, Asia/Kolkata). Month-end and leap-year safe. Idempotent and concurrency-safe (see below). Catch-up bills every missed period; failures are logged and retryable without skipping or duplicating. |
| **Taxes** | Percentage or fixed-per-unit rules configured by the admin, applied per line on the post-discount amount, half-up rounding to paise. |
| **Discounts** | Fixed or percentage; whole subscription or specific products; min purchase, min quantity, date window, usage limit, optional subscription targeting. Applied automatically to the next qualifying invoice; never makes a total negative. |
| **Invoices** | Draft → Confirmed → Paid, plus Cancel. Confirm, cancel, send, print, PDF download. Tax and discount breakdown per line. |
| **Payments** | Method, amount, date, reference, note, recording user. Partial payments supported; overpayment rejected; duplicate references rejected; invoice becomes Paid only when the balance reaches zero. Admin can void with a reason. |
| **Customer portal** | Dashboard, subscriptions, plan details, renewal dates, invoices + PDF, payment history, profile, and self-service pause / resume / renew where the plan allows. |
| **Dashboard & reports** | KPIs (MRR, collected vs invoiced, outstanding, overdue, renewals…), revenue trend, active-subscription trend, status distributions, aging, renewal overview, billing activity. Every KPI and chart segment drills down to the filtered records. Five reports with date/plan filters and CSV export. |
| **Automation & admin** | Billing, auto-close, renewal reminders, overdue scan and discount housekeeping jobs with a run history; audit log; email outbox; users and tax management; settings. |

## Technology

- **Backend:** Python 3.12+ · FastAPI · SQLAlchemy 2 · Alembic · Pydantic 2 · APScheduler · ReportLab (PDF)
- **Database:** PostgreSQL 14+ (16 used in development)
- **Frontend:** React 19 · TypeScript · Vite · Tailwind CSS · TanStack Query · Recharts · lucide icons
- **Tests:** pytest against a real PostgreSQL database; Playwright used for UI verification

## Project structure

```
backend/
  app/
    core/         config, database, security, auth dependencies, business clock, money helpers
    models/       SQLAlchemy models (27 tables)
    schemas/      Pydantic request/response models
    services/     business logic: subscriptions, billing, invoices, discounts, payments, pricing, periods, reports, pdf
    api/          HTTP routers (thin — they call services)
    automation/   scheduled jobs + scheduler
    seed.py       Brightloop demo data (+ --bulk N for load testing)
    main.py       FastAPI app
  migrations/     Alembic migrations
  tests/          79 tests (auth, catalog, periods, lifecycle, billing, concurrency, discounts, payments, portal, reports, E2E)
frontend/
  src/
    components/   UI kit, charts, line editor, customer picker, logo
    layouts/      app shell (sidebar, search, notifications, profile)
    lib/          API client, auth, hooks, formatting, types
    pages/        Overview, Customers, Catalog, Subscriptions/Quotations, Billing (invoices, payments, discounts), Reports, Admin, Portal, Auth
```

## Getting started

### Prerequisites
- Python 3.12 or newer
- Node.js 20 or newer
- PostgreSQL 14 or newer.

### 1. Database
```bash
sudo -u postgres psql -c "CREATE USER subsy WITH PASSWORD 'subsy' CREATEDB;"
sudo -u postgres psql -c "CREATE DATABASE subsy OWNER subsy;"
sudo -u postgres psql -c "CREATE DATABASE subsy_test OWNER subsy;"   # for the test suite
```

### 2. Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # set SUBSY_SECRET_KEY; adjust DATABASE_URL if needed
alembic upgrade head            # create the schema
python -m app.seed              # Brightloop demo data (safe to re-run; it won't duplicate)
uvicorn app.main:app --reload --port 8000
```
API docs: http://localhost:8000/docs

### 3. Frontend
```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173 (proxies /api to :8000)
```
Production build: `npm run build` → static files in `frontend/dist/` (serve them and proxy `/api` to the backend).

### Demo accounts
After `python -m app.seed` — password for all: **`Subsy@Demo2026`**

| Role | Email |
|---|---|
| Admin | `admin@brightloop.demo` |
| Internal staff | `staff@brightloop.demo` (also `finance@brightloop.demo`) |
| Customer (portal) | `priya@sparkshop.demo` |

The login page has buttons that fill these in. All demo records are flagged `is_demo` and shown with a small **DEMO** tag.

The demo dataset is produced by *replaying* 12 months of business through the real services (quotes, confirmations,
activations, the billing engine, payments, pauses, closures, renewals). Dashboard numbers are therefore real
aggregates of real records, not hard-coded values.

## Running tests
```bash
cd backend
pytest                          # uses SUBSY_DATABASE_URL or postgresql://subsy:subsy@localhost/subsy_test
```
The suite (79 tests, ~2½ minutes) truncates the test database between tests. It covers the PS password rules,
role restrictions, customer data isolation, variant pricing, every billing frequency including month-end and
leap-day anchors, the full lifecycle, pause/resume, renewal, auto-close, duplicate-billing prevention under
**concurrent runners**, failure recovery, discounts (limits, windows, minimums, release on cancel), partial /
over- / duplicate payments, overdue detection, report reconciliation, and the 20-step acceptance journey.

Frontend type-check: `cd frontend && npx tsc -b`.

## How billing stays correct

1. **`UNIQUE(subscription_id, period_start)`** on `billing_events` — a period can have only one billing event.
2. **`UNIQUE(billing_event_id)`** on `invoices` — a billing event can have only one invoice.
3. **Row lock per subscription** (`SELECT … FOR UPDATE SKIP LOCKED`) — concurrent runners never work on the same subscription.
4. **Postgres advisory lock** — only one scheduled billing run at a time.
5. **Index advances only after the invoice commits** — a failure leaves the event `failed` and the period open;
   the next run or a manual *Retry* bills exactly that period. Nothing is skipped, nothing is doubled.

Periods are always computed from the subscription's anchor date (never chained), so a subscription starting on
31 January bills on 28/29 Feb, 31 Mar, 30 Apr… and a yearly one anchored on 29 Feb bills on 28 Feb in non-leap years.

## Business rules (documented decisions)

- **Pricing:** catalog price = product sales price + variant adjustment; a quotation line may override it. The
  agreed price is snapshotted on the subscription line and used for every invoice.
- **Discounts:** percentage = eligible amount × value / 100; fixed = min(value, eligible amount). Several rules can
  stack, each capped so no line goes below zero. Taxes are computed after discounts.
- **Discount usage:** a draft invoice *reserves* a use, confirming *consumes* it, cancelling *releases* it. Usage is
  tied to the invoice (and the invoice to a unique billing event), so retried jobs can't double-count.
- **Payments:** each payment is allocated to exactly one invoice. Partial payments are allowed;
  outstanding = total − posted payments; overpayment is rejected (no customer-credit balance).
- **Pause:** periods that *start* while paused are not billed; earlier unbilled periods remain due.
- **Renewal:** extends the expiry by one plan term; each term can be renewed once (DB-enforced).
- **Final period:** if the expiry falls mid-period, the last invoice covers up to the expiry date at the full
  period price (no proration).
- **Invoice confirmation:** generated invoices are drafts for staff review by default; an admin setting can
  auto-confirm them.
- **Revenue:** *invoiced* = confirmed + paid invoices by invoice date; *collected* = posted payments by payment
  date. Outstanding invoices are never counted as collected revenue.

## Email

With `SUBSY_SMTP_HOST` set, Subsy sends email over SMTP. **Without it, no email is sent.** Each message is recorded
in **Administration → Email outbox** with status `not_sent`, and the UI says so explicitly (e.g. the password
reset screen and the invoice *Send* action). In development, an admin can copy a password-reset link from the outbox.

## Performance

Measured on the development container (PostgreSQL 16, single API worker, warm cache) with **5,021 subscriptions,
5,014 customers and 5,134 invoices** (`python -m app.seed --bulk 5000`). Best of 3 requests:

| Endpoint | Time |
|---|---|
| Dashboard (all KPIs + charts) | 144 ms |
| Revenue / subscriptions / invoices reports | 162–167 ms |
| Subscription list (page 1 / search, page 40) | 27 ms / 82 ms |
| Invoice list, overdue filter | 21–24 ms |
| Customer list / search | 40–52 ms |
| Subscription detail, global search, payments | 16–24 ms |

All measured pages are well under the PS's 2-second target. Every list is paginated and filtered on the server.
Each response includes an `X-Response-Time` header, and requests slower than 2 s are logged as warnings.

**Billing throughput:** 5,010 subscriptions falling due on the same day were invoiced in 139 s (≈36 invoices/s;
0 failures, 0 duplicate periods; an immediate re-run created 0 invoices). This runs as a background job and does not
block pages, but very large single-day volumes would benefit from batching (see Known limitations).

## Known limitations

- **No payment gateway.** Payments are recorded by staff; there is no online card/UPI checkout.
- **Email** needs SMTP configuration; there is no queue or retry for failed sends.
- **Billing throughput** is ~36 invoices/s with one worker (per-subscription transactions). Fine for hundreds or a
  few thousand per day; tens of thousands would want parallel workers or batched inserts.
- **No proration** for mid-period changes or early closure, and no credit notes. Overpayments are rejected rather than held as credit.
- **Single currency (INR)** and a single company.
- **Taxes** are one rule per product line (e.g. GST 18%), not split CGST/SGST/IGST by place of supply.
- **Sessions** use bearer tokens in `localStorage`. This avoids CSRF but is exposed to XSS; httpOnly cookies would be stronger.
- **No rate limiting** on login or reset endpoints.
- **Frontend** has no automated component tests. UI flows were verified with Playwright scripts during development (not committed as a suite).
- **Demo data** history is replayed over the 12 months before the day you run the seed. Audit-log timestamps follow the replayed dates.

See [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md) for the requirement-by-requirement status.

---
**Project:** Subsy · **Tagline:** Every Subscription, Simplified.
