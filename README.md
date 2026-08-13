# Vellox ERP Next

**Open-source ERP for media & creative agencies, built on Frappe + ERPNext.**

A custom Frappe app that turns ERPNext into an agency-first ERP: clients, retainers,
projects, campaigns, media buying, content production, time tracking, and billing —
in one system.

Built for [Vellox Studio](https://www.velloxstudio.com), open for all.

## Features

| Module | What it does |
|--------|--------------|
| **Clients & Projects** | `Client Account`, `Engagement` (retainer/one-off), `Agency Project` with scope, deliverables, project members |
| **Campaign & Media Buying** | `Agency Campaign`, `Ad Platform Account`, `Placement` and `Media Spend` child tables, budget vs actual |
| **Content Production** | `Production Job` with tasks, `Production Asset` versioning, `Revision`, `Approval Request` |
| **Invoicing & Billing** | `Agency Invoice` (auto-computed totals), `Invoice Line`, `Retainer`, `Expense` |
| **Timesheets & Resource** | `Agency Timesheet` (auto total/billable), `Capacity Plan`, `Skill` matrix |
| **Reports & Dashboard** | Script reports: `Agency KPI`, `Budget vs Actual`, `Agency Utilization`, `Production Pipeline`, `Invoice Register` + a `Vellox Agency` desk workspace |

## Tech Stack

- **Frappe** v15 / **ERPNext** v15 (installed as standard apps — this project is a custom app, not a fork)
- Python 3.11 / MariaDB / Redis
- MIT License — free to use, modify, and resell services around

## Getting Started

```bash
# 1. Install Frappe Bench (https://frappeframework.com/docs/v15/user/en/installation)
bench init frappe-bench --frappe-branch version-15
cd frappe-bench

# 2. Add ERPNext and this app
bench get-app erpnext --branch version-15
bench get-app https://github.com/bhamalawi-alt/Vellox-ERP-Next
bench new-site yoursite.local --install-app erpnext --install-app vellox_agency

# 3. Run
bench --site yoursite.local serve
```

The `vellox_agency` app ships inside this repo under `apps/vellox_agency/`.

## Repo Layout

```
vellox-erp-next/
├── apps/vellox_agency/     # the Frappe app (custom DocTypes, reports, workspace)
├── docs/                   # project plan + user docs
├── LICENSE                 # MIT
└── README.md
```

## Status

MVP in active development — modules above are implemented and verified on a live
bench (Frappe v15 + ERPNext v15). Roadmap and milestones live in `docs/PROJECT_PLAN.md`.

## Credits

Built on [Frappe](https://frappeframework.com) and [ERPNext](https://erpnext.com).
"Vellox ERP Next" is an independent open-source project by Vellox Studio.
