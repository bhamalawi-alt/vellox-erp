# Vellox ERP Next

**An ERPNext add-on that runs a creative studio: from website inquiry to
quote, project, deliverables and change control.**

`vellox_agency` is a custom Frappe app installed on top of a standard ERPNext
site (not a fork). ERPNext stays the source of truth for customers, quotes,
projects, tasks, timesheets, invoices, payments and the ledger; the app adds
the studio's own rules around them.

Built for [Vellox Studio](https://www.velloxstudio.com), open for all.
Delivery is tracked on the Trello board *Vellox ERP Delivery*; every change
lands through a reviewed pull request with green CI.

## What works today

Everything below is on `master`, covered by the app's test suite, and built on
standard ERPNext records.

| Area | What it does | Built on |
|---|---|---|
| **Website inquiries** | Public intake endpoint `vellox_agency.api.intake.submit_inquiry` (open to guests) with a honeypot, limits per visitor (5/hour, IPv6 per /64) and per mailbox (3/day), and repeat inquiries merged into the existing Lead. The prospect gets an acknowledgement email | Lead |
| **Lead follow-up** | Each Lead gets a 4-hour first-reply deadline; new Leads are assigned round-robin to active Vellox Sales users who can see every Lead, or to Agency Managers if no salesperson qualifies (routing switches itself off if nobody does); a daily email to Operations lists leads still waiting for a reply | Lead, Assignment Rule |
| **Sales pipeline** | An Opportunity created from a Lead needs that Lead marked Qualified; four sales stages carry win probabilities (10/30/60/80%); a lost reason is required; each owner gets a daily list of opportunities with no update in 14 days | Opportunity, Sales Stage |
| **Quotes** | Seven service Items with EGP and USD price lists; a technical proposal built from the selected services; an estimate panel (hours, rates, vendor cost) showing margin; three print formats (technical, financial, combined) | Quotation, Item |
| **Quote approval** | Three tiers by discount and margin: automatic (discount ≤5% and margin ≥40%), Operations (≤15% and ≥25%), otherwise Agency Manager. Outside the automatic tier, the **Approve Quote** button is the only way to approve, and any change to customer, items, prices, discounts, taxes or margin sends the quote back to Pending. Submitting needs an approval | Quotation |
| **Projects** | **Create Project** from a submitted quote; its tasks come from the seven practice templates (ordered steps, milestones, dependencies, default roles). A project can also be created from a template through the API. A quote's expected margin is frozen on the project. Projects have Health (managers only), Phase (follows the tasks), Project Manager and Risks, with change history | Project, Task, Project Template |
| **Deliverables** | Status, immutable versions (enforced on save), review rounds, a revision allowance (when it is used up, the Agency Manager gets an alert) and a client-visible flag that limits what client users see. The status order and the revision-allowance block are not yet enforced on the form ([P3-146]) | `Deliverable` (+ version and review-round tables) |
| **Change requests** | Moving a request from Under Review to Approved needs a Project Manager, or the Agency Manager when the price changes; approval moves the project end date by the schedule impact; a price change needs a submitted amendment quote before the request is marked Implemented. A request saved straight as Approved still skips these checks ([P3-146]) | `Vellox Change Request` |
| **Team capacity** | Staff and freelancers (Frappe HR Employees) have daily hours, a utilization target (75%) and seniority; available hours come from the Holiday List and approved leave. People are booked on projects for hours a week; the *Vellox Team Capacity* report shows available, booked, free and overbooked hours per Monday-to-Sunday week (a part-week booking counts its share of working days), plus a separate *likely* line by role from open deals. Overbooking warns but does not block. The same report shows billable hours and utilization % (submitted billable timesheet hours ÷ available hours). Team members see only their own capacity; Sales sees only the likely line (*Vellox Likely Demand* report) | Employee, Holiday List, Leave Application, `Vellox Resource Allocation` |
| **Project profit** | Per project, in USD at each document's date: contract value (the quote plus approved change-request amendment quotes), budget (the quotes' estimates), actual cost (submitted timesheets, vendor Purchase Invoices, approved Expense Claims), remaining cost (open tasks' *Remaining Hours* × the assignee's cost rate, plus vendor cost still to come), forecast final cost, expected margin and drift from the quoted margin, with a Green / Amber / Red signal (amber: margin under 25% or more than 10 points below the quote; red: under 10% or forecast over the price). The *Vellox Project Profit* report shows the amounts to Finance and the Agency Manager only; Project Managers (their own projects) and Operations see budget used %, margin drift and the colour, which a daily job also stores on each open project | Project, Task, Timesheet, Purchase Invoice, Expense Claim |
| **Alerts** | Email notifications for: inquiry acknowledgement (to the prospect), quote approved by hand (to its creator), project created (to its PM), deliverable sent to client review, client decision, Change Request decision (project team), revision allowance used up | Notification |
| **Access by job** | Role profiles for Sales, Project Manager, Team Member, Finance, Operations and Agency Manager. Each job sees only what it needs (invoices, payments, orders and accounts, plus cost rates and the cost, billing and margin amounts on projects, tasks and timesheets, stay with Finance and the Agency Manager), team members see only their projects, and sharing or assigning cannot give anyone more than their job allows | Role Profile, permission hooks |
| **Workspace** | A *Vellox Agency* desk workspace with shortcuts to clients, projects, timesheets, invoices and offers | Workspace |
| **Scheduled jobs** | Hourly: lead-routing sync and removal of shares beyond a person's job. Daily: late-reply digest and stale-opportunity reminders (each sent at most once a day), and the project profit refresh | Frappe scheduler |

### Not in use

The original prototype DocTypes are kept only so old data stays readable.
They are **not** part of the product; see [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md).

- **Retired and blocked** (new records refused; use the ERPNext record instead):
  `Client Account`, `Engagement`, `Agency Project`, `Agency Timesheet`,
  `Agency Invoice`, `Expense`, `Retainer`. The mapping is in
  [docs/migrations/deprecation-map.md](docs/migrations/deprecation-map.md).
- **Prototype, never built out** (no business logic, not on the workspace):
  campaigns and media buying, content production, capacity plans. (The
  prototype skills DocTypes were removed in [P4-102]; Frappe HR's Skill replaces them.)
- **Disabled reports**: `Agency KPI`, `Agency Utilization`, `Budget vs Actual`,
  `Invoice Register`, `Production Pipeline` read the retired or prototype
  DocTypes and are turned off.

## Tech stack

- **Frappe** v15 / **ERPNext** v15 / **Frappe HR** (hrms) v15, installed as standard apps
- Python 3.11, Node 20, MariaDB 10.6, Redis
- MIT License

## Supported versions

| App | Supported range | Tested |
|---|---|---|
| Frappe | `>=15.118.0,<16` | 15.125.0 |
| ERPNext | `>=15.119.1,<16` | 15.124.3 |
| Frappe HR (hrms) | `>=15.64.0,<16` | 15.64.7 |

Frappe/ERPNext/Frappe HR **v16 is out of scope.** A compatibility gate runs before every
migration: unsupported combinations fail with an actionable message instead of
producing a broken site.

### Upgrade policy

1. Stay on the `version-15` branch of both upstream apps.
2. Before upgrading, run `scripts/verify_clean_install.sh` against the target versions.
3. Upgrade one app at a time (`bench switch-to-branch`, `bench update`) and rerun the app test suite.
4. v16 support will be delivered as a separate, announced release, never implicitly.

## Getting started

This repository root *is* the installable Frappe app (`vellox_agency`).

```bash
# 1. Install Frappe Bench (https://frappeframework.com/docs/user/en/installation)
bench init frappe-bench --frappe-branch version-15 --python python3.11
cd frappe-bench

# 2. Add ERPNext, Frappe HR and this app
bench get-app erpnext --branch version-15
bench get-app hrms --branch version-15
bench get-app https://github.com/bhamalawi-alt/vellox-erp
bench new-site vellox.localhost --install-app erpnext --install-app hrms --install-app vellox_agency

# 3. Apply the Vellox setup (roles, fields, notifications, templates)
bench --site vellox.localhost migrate

# 4. Run
bench start
```

Step 3 matters: install skips most of the Vellox setup, which runs after every
migrate (`vellox_agency.security.apply_baseline`).

**Upgrading a site created before Frappe HR was required** ([P4-102]): fetch
hrms, migrate first, then install it. The migrate removes the app's old
prototype `Skill` DocTypes, so Frappe HR's own `Skill` can take their place.

```bash
bench get-app hrms --branch version-15
bench --site vellox.localhost migrate
bench --site vellox.localhost install-app hrms
bench --site vellox.localhost migrate
```

### Local development recipe

The development machine runs MariaDB in Docker rather than installing it:

```bash
docker run -d --name vellox-mariadb -p 127.0.0.1:3306:3306 \
  -e MARIADB_ROOT_PASSWORD=<choose-one> mariadb:10.6 \
  --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci
```

- Development site: `vellox.localhost`.
- A **separate test site** with `allow_tests` set; run tests there, never on the
  development site, because some tests change shared settings:

  ```bash
  bench new-site vellox-test.localhost --install-app erpnext --install-app hrms --install-app vellox_agency
  bench --site vellox-test.localhost set-config allow_tests true
  bench --site vellox-test.localhost migrate
  bench --site vellox-test.localhost run-tests --app vellox_agency
  ```

- On the development site, set `mute_emails` and add a placeholder outgoing
  Email Account: ERPNext emails project members when they are added and fails
  without an account.

More on each environment: [docs/environments.md](docs/environments.md).

### Clean-install verification

```bash
export MARIADB_ROOT_PASSWORD=...   # your local MariaDB root password
scripts/verify_clean_install.sh    # optional args: [repo_url] [branch]
```

It builds a scratch bench, installs the app from the given URL, migrates,
uninstalls and reinstalls the app, and runs the test suite.

## CI and local equivalents

CI (`.github/workflows/ci.yml`) runs on every pull request and every push to
master. Each step maps to a local command:

| CI step | Local equivalent |
|---|---|
| Init bench + fetch apps + clean site | `scripts/verify_clean_install.sh` |
| Migrate | `bench --site vellox-test.localhost migrate` |
| Python compilation | `python -m compileall -q vellox_agency` |
| JavaScript tests | `node --test vellox_agency/tests/js/*.js` |
| Frappe tests | `bench --site vellox-test.localhost run-tests --app vellox_agency` |
| Whitespace check | `git diff --check` |

CI creates a throwaway database in an ephemeral MariaDB container; no
credentials or site configuration are stored in this repository.

## Repo layout

```
vellox-erp/                  # repository root = installable Frappe app
├── vellox_agency/           # the Python package: hooks, setup, DocTypes, tests
├── docs/                    # project plan, audit, specs, plans, runbooks
├── scripts/                 # verification, backup, restore and deploy scripts
├── pyproject.toml           # app packaging metadata
├── LICENSE                  # MIT
└── README.md
```

## Credits

Built on [Frappe](https://frappeframework.com) and [ERPNext](https://erpnext.com).
"Vellox ERP Next" is an independent open-source project by Vellox Studio.
