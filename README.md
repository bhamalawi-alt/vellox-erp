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
| **Website inquiries** | Guest-only intake endpoint `vellox_agency.api.intake.submit_inquiry` with a honeypot, limits per visitor (5/hour, IPv6 per /64) and per mailbox (3/day), and repeat inquiries merged into the existing Lead. The prospect gets an acknowledgement email | Lead |
| **Lead follow-up** | Each Lead gets a 4-hour first-reply deadline; new Leads are shared round-robin among active Vellox Sales / Agency Manager users who can see Leads (routing switches itself off if nobody qualifies); a daily email lists leads still waiting for a reply | Lead, Assignment Rule |
| **Sales pipeline** | Opportunities need a qualified Lead; four sales stages carry win probabilities (10/30/60/80%); a lost reason is required; each owner gets a daily list of opportunities with no update in 14 days | Opportunity, Sales Stage |
| **Quotes** | Seven service Items with EGP and USD price lists; a technical proposal built from the selected services; an estimate panel (hours, rates, vendor cost) showing margin; three print formats (technical, financial, combined) | Quotation, Item |
| **Quote approval** | Three tiers by discount and margin (automatic / Operations / Agency Manager). An **Approve Quote** button is the only way to approve, and any change to customer, items, prices, discounts, taxes or margin sends the quote back to Pending. Submitting needs an approval | Quotation |
| **Projects** | **Create Project** from a submitted quote, or from one of seven practice templates with ordered steps, milestones, dependencies and default roles. Expected margin is frozen at creation. Projects have Health (managers only), Phase (follows the tasks), Project Manager and Risks, with change history | Project, Task, Project Template |
| **Deliverables** | Draft → internal review → client review → approved, with immutable versions, review rounds, a revision allowance that requires a Change Request once used up, and a client-visible flag | `Deliverable` (+ version and review-round tables) |
| **Change requests** | Approval by role (Agency Manager when the price changes), schedule impact moves the project end date, and a price impact needs a submitted amendment quote | `Vellox Change Request` |
| **Alerts** | Email notifications for: inquiry received, quote approved, project created, deliverable sent to client review, client decision, Change Request decision (project team), revision allowance used up | Notification |
| **Access by job** | Role profiles for Sales, Project Manager, Team Member, Finance, Operations and Agency Manager. Each job sees only what it needs (money and cost data stay with Finance and managers), team members see only their projects, and sharing or assigning cannot give anyone more than their job allows | Role Profile, permission hooks |
| **Workspace** | A *Vellox Agency* desk workspace with shortcuts to clients, projects, timesheets, invoices and offers | Workspace |
| **Scheduled jobs** | Hourly: lead-routing sync and removal of shares beyond a person's job. Daily: late-reply digest and stale-opportunity reminders (each sent at most once a day) | Frappe scheduler |

### Not in use

The original prototype DocTypes are kept only so old data stays readable.
They are **not** part of the product; see [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md).

- **Retired and blocked** (new records refused; use the ERPNext record instead):
  `Client Account`, `Engagement`, `Agency Project`, `Agency Timesheet`,
  `Agency Invoice`, `Expense`, `Retainer`. The mapping is in
  [docs/migrations/deprecation-map.md](docs/migrations/deprecation-map.md).
- **Prototype, never built out** (no business logic, not on the workspace):
  campaigns and media buying, content production, capacity plans and skills.
- **Disabled reports**: `Agency KPI`, `Agency Utilization`, `Budget vs Actual`,
  `Invoice Register`, `Production Pipeline` read the retired ledgers and are
  turned off.

## Tech stack

- **Frappe** v15 / **ERPNext** v15, installed as standard apps
- Python 3.11, Node 20, MariaDB 10.6, Redis
- MIT License

## Supported versions

| App | Supported range | Tested |
|---|---|---|
| Frappe | `>=15.118.0,<16` | 15.125.0 |
| ERPNext | `>=15.119.1,<16` | 15.124.3 |

Frappe/ERPNext **v16 is out of scope.** A compatibility gate runs before every
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

# 2. Add ERPNext and this app
bench get-app erpnext --branch version-15
bench get-app https://github.com/bhamalawi-alt/vellox-erp
bench new-site vellox.localhost --install-app erpnext --install-app vellox_agency

# 3. Apply the Vellox setup (roles, fields, notifications, templates)
bench --site vellox.localhost migrate

# 4. Run
bench start
```

Step 3 matters: install skips most of the Vellox setup, which runs after every
migrate (`vellox_agency.security.apply_baseline`).

### Local development recipe

The development machine runs MariaDB in Docker rather than installing it:

```bash
docker run -d --name vellox-mariadb -p 3306:3306 \
  -e MARIADB_ROOT_PASSWORD=<choose-one> mariadb:10.6 \
  --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci
```

- Development site: `vellox.localhost`.
- A **separate test site** with `allow_tests` set; run tests there, never on the
  development site, because some tests change shared settings:

  ```bash
  bench new-site vellox-test.localhost --install-app erpnext --install-app vellox_agency
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
