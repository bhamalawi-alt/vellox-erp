# Duplicate Ledger Deprecation Map

**Card:** [P0-06] · **Date:** 2026-08-25 · **Status:** active policy
**Baseline measurement (2026-08-25, site `vellox.localhost`):**

| Deprecated ledger | Records at baseline |
|---|---|
| Client Account | 0 |
| Agency Project | 0 |
| Agency Timesheet | 0 |
| Expense | 0 |
| Agency Invoice | 0 |
| Engagement | 0 |
| Retainer | 0 |

All parallel ledgers are empty; the prototype never held operational data.
The counts above are re-logged on every migration by patch
`vellox_agency.patches.deprecate_duplicates` (idempotent) into the
`vellox_deprecation_audit` logger.

## Policy

1. **Blocked from today:** new inserts and deletions in the ledgers below
   raise a validation error naming the ERPNext target (hook `doc_events`,
   see `vellox_agency/deprecations.py`). Install/migrate/patch/test contexts
   remain exempt so metadata operations and tests keep working.
2. **Read-only retention:** existing rows (none today) stay readable until an
   explicit retention-approval decision deletes them in a later release.
3. **No data deletion in this release.**
4. **Real data movement is rehearsed under [P8-49]** using the mappings below,
   before any production deployment.

## Source → target field mapping

### Client Account → Customer (+ Contact + Address)

| Client Account field | ERPNext target |
|---|---|
| client_name | Customer.customer_name |
| client_type (if set) | Customer.customer_type |
| email / phone / mobile (as present) | Contact.email_ids / phone + Dynamic Link to Customer |
| billing/shipping address fields (as present) | Address (+ Dynamic Link to Customer) |
| status | Customer.disabled (Open→0, Closed→1) or Customer Group per contract |
| notes | Customer (Dashboard/Notes via standard Comment) |

### Agency Project → Project

| Agency Project field | ERPNext target |
|---|---|
| project_name | Project.project_name |
| client_account | Project.customer |
| start_date / end_date | Project.expected_start_date / expected_end_date |
| budget fields | Project.total_budget_margin / custom budget extension (approved later phase) |
| members | Project Users child table |
| deliverable/scope children | later approved delivery model ([P3-*]) — not migrated blindly |

### Agency Timesheet → Timesheet

| Agency Timesheet field | ERPNext target |
|---|---|
| user | Timesheet.employee (via Employee linked to that User) |
| entries[].activity | Time Logs.activity_type |
| entries[].hours | Time Logs.hours |
| entries[].project/date | Time Logs.project / from_time |
| billable flag | Time Logs.billing_hours + Sales Invoice Item linkage |

### Expense → Expense Claim (staff) or Purchase Invoice (vendor)

| Expense field | ERPNext target |
|---|---|
| vendor (free text) | Supplier (resolved/created) on Purchase Invoice |
| employee-linked rows | Expense Claim with claimed amount |
| amount / currency | grand_total with company currency conversion |
| project link | cost center / project dimension on the accounting document |

### Agency Invoice → Sales Invoice

| Agency Invoice field | ERPNext target |
|---|---|
| customer fields | Sales Invoice.customer |
| invoice_line items | Sales Invoice Items (Item = service Item) |
| totals | recalculated by ERPNext — never copied totals |
| payment_status | Payment Entry reconciliation against submitted Sales Invoice |

### Engagement / Retainer → approved ERPNext-backed model

Quotation (offer) + Subscription/contract pattern per the approved Offer
Builder design and future retainer specification ([P5-*]). No field mapping
is frozen yet; these two ledgers are blocked for new use immediately.

## Rollback strategy

1. The guard lives in one hook block (`doc_events` in `hooks.py`) plus one
   module (`deprecations.py`). Removing them restores previous behavior.
2. The deprecation patch only *logs*; it mutates no business data, so
   "rollback" of data is trivially unnecessary at zero baseline counts.
3. If real data existed at migration time, rollback would be: restore the
   pre-migration site backup (`bench --site <site> backup` taken by the runbook)
   — backups precede every migration step per bench safety rules.

## Reconciliation rule

After any future data movement: per-ledger row counts and financial sums
(amount × qty where applicable, converted to company currency) must match
between source rows and created ERPNext documents, verified twice (migration
run twice; second run changes nothing).
