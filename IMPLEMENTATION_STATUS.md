# Subsy — Implementation status

Last updated: 31 Oct 2026 · Architecture: FastAPI + SQLAlchemy + PostgreSQL / React + TypeScript + Vite

**Status key:** NOT STARTED · IN PROGRESS · IMPLEMENTED (code exists, not fully tested) · TESTED (automated tests pass)
· **VERIFIED** (implemented, connected, tests pass, workflow checked in the running app, data persists, permissions checked)

## Summary

| Module | Status | Evidence |
|---|---|---|
| Authentication & registration | VERIFIED | `tests/test_auth.py` (17 tests) · login/register/reset screens checked in browser |
| Roles & authorisation | VERIFIED | role tests, isolation tests, E2E step 20 · nav and buttons per role checked |
| Products & variants | VERIFIED | `test_catalog_and_periods.py` · product editor used in browser |
| Plans & billing frequencies | VERIFIED | period tests (month-end, leap year, intervals) · plan cards/editor in browser |
| Quotation templates & quotations | VERIFIED | `test_subscriptions.py` · created from template through the UI (Playwright flow) |
| Subscription lifecycle | VERIFIED | lifecycle, invalid-transition, pause/resume, renew, auto-close tests · UI flow |
| Recurring billing engine | VERIFIED | `test_billing.py` (13 tests incl. concurrency + failure recovery) · 5,010-subscription run |
| Duplicate-billing prevention | VERIFIED | DB constraints + concurrent-runner tests + re-run in perf test (0 duplicates) |
| Taxes | VERIFIED | tax math asserted in billing/discount/E2E tests · admin tax screen |
| Discounts | VERIFIED | `test_discounts_payments.py` (8 discount tests) · discount screens |
| Invoices (confirm/cancel/send/print/PDF) | VERIFIED | invoice tests, PDF test · UI flow confirmed an invoice |
| Payments & allocation | VERIFIED | partial/full/over/duplicate/void tests · UI flow: partial then full → Paid |
| Customer portal | VERIFIED | `test_portal_reports.py` isolation + self-service · portal pages checked as customer |
| Dashboard | VERIFIED | reconciliation test · rendered with seed data, drill-down links |
| Reports & CSV export | VERIFIED | reconciliation + all-reports tests · five report tabs rendered |
| Automation (scheduler + jobs) | VERIFIED | auto-close test runs `run_daily` · scheduler starts with app · run history UI |
| Notifications | TESTED | auto-confirm test asserts customer notification · bell UI renders |
| Audit log | IMPLEMENTED | written on all critical actions · admin view renders; no dedicated test |
| Email (SMTP) | IMPLEMENTED | outbox path tested; **real SMTP delivery not tested** (no server in dev) |
| Performance target (< 2 s) | VERIFIED | measured 16–167 ms on 5,021 subscriptions (see README) |
| Responsive UI | VERIFIED | 390 px mobile screenshots: overview, lists, invoice (table scrolls inside card) |
| Demo data | VERIFIED | idempotent seed (re-run is a no-op), replayed through services |
| Frontend automated tests | NOT STARTED | UI verified with ad-hoc Playwright scripts only |
| Rate limiting on auth endpoints | NOT STARTED | — |
| Payment gateway | NOT STARTED | out of scope; manual payment recording only |

## Requirement checklist (PS + build brief)

### Authentication & roles
- [x] Unique email per account (DB unique + case-insensitive check) — VERIFIED
- [x] Password > 8 chars, upper, lower, special — enforced on server and shown live in UI — VERIFIED
- [x] Reset link to registered email; expiring (30 min), single-use, hashed token — VERIFIED (delivery via outbox unless SMTP set)
- [x] Admin / internal staff / customer roles, server-side enforcement — VERIFIED
- [x] Only admin can create staff — VERIFIED
- [x] Staff cannot manage discounts, taxes, products, plans, users — VERIFIED
- [x] Customers see only their own subscriptions, invoices, payments — VERIFIED
- [x] Logout / password change revoke existing sessions — VERIFIED

### Products & plans
- [x] Product name, type, sales price, cost price, notes, tax, archive — VERIFIED
- [x] Variants with configurable price adjustment (e.g. Odoo +560), duplicates prevented — VERIFIED
- [x] Plan price, billing (daily/weekly/monthly/yearly + interval), min quantity, availability dates — VERIFIED
- [x] Auto-close / early close / pause / renew per plan, enforced for staff and customers — VERIFIED

### Quotations & subscriptions
- [x] Quotation templates with plan, product lines, validity days — VERIFIED
- [x] Subscription number, customer, plan, start, expiry, payment terms, lines (product, qty, unit price, taxes, amount) — VERIFIED
- [x] Draft → Quotation → Confirmed → Active → Closed with validated transitions + history — VERIFIED
- [x] Expired quotations blocked until extended; confirmed quotations locked — VERIFIED
- [x] Pause/resume, renewal (once per term), early closure, automatic closure — VERIFIED
- [x] Upcoming / expiring / expired renewal views — VERIFIED

### Billing, taxes, discounts
- [x] Scheduled invoice generation with customer, lines, taxes, discounts, totals — VERIFIED
- [x] Invoice Draft → Confirmed → Paid; cancel; send; print; PDF — VERIFIED
- [x] No duplicate or skipped billing, including concurrent runs and retries — VERIFIED
- [x] Failed billing recorded and retryable — VERIFIED
- [x] Admin-configured tax rules applied automatically — VERIFIED
- [x] Fixed / percentage discounts; min purchase, min quantity, dates, usage limit; products or whole subscription — VERIFIED
- [x] Discount appears automatically on the next invoice and stops when expired or exhausted — VERIFIED

### Payments & reporting
- [x] Payment method, amount, date, note, against the right invoice — VERIFIED
- [x] Paid vs outstanding vs overdue at any moment — VERIFIED
- [x] Dashboard: active subscriptions, revenue, payments, overdue, with filters and summary — VERIFIED
- [x] Reports: subscriptions, revenue, invoices, payments, discounts; CSV export — VERIFIED
- [x] Pages under 2 s with thousands of subscriptions — VERIFIED (measured)

## Test results
```
cd backend && pytest
79 passed (auth 17, catalog/periods 15, subscriptions 11, billing 13, discounts/payments 17, portal/reports 5, E2E 1)
frontend: npx tsc -b → 0 errors · npm run build → OK
```

## Issues found and fixed during verification
- Scheduler failed to start where the OS time zone was `Asia/Calcutta` → cron trigger now pinned to `Asia/Kolkata`.
- Invoice page overflowed horizontally on phones → grid children may shrink; wide tables scroll inside their card.
- The new-quotation customer dropdown only loaded 200 customers and could not find most of 5,000 → replaced with a server-side search picker (same fix for the discount's subscription chooser).
- Replayed demo history stamped records with the real date → timestamps now follow the business clock during replay and tests.

## Next steps (if continuing)
1. Frontend component/E2E test suite (commit the Playwright flows).
2. Rate limiting on login and password-reset endpoints.
3. Batched/parallel billing workers for very large single-day volumes.
4. Credit notes, proration and customer credit balances.
5. Split GST (CGST/SGST/IGST) by place of supply.
