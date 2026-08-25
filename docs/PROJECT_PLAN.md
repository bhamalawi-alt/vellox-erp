# Vellox ERP Next — Project Plan

**Open-source ERP for media / creative agencies, built on Frappe + ERPNext.**

- **Company:** Vellox Studio (https://www.velloxstudio.com) — business development studio
  (Brand Strategy, Identity, UX, Visual Content, Web Dev, eCommerce, Mobile Apps)
- **Repository name:** `vellox-erp`
- **License:** MIT (open source, business-friendly)
- **Base stack:** Frappe framework + ERPNext (Python 3.11 / MariaDB / Redis / Node)

---

## 1. Vision

ERPNext is the most mature open-source ERP, but it is built for product/manufacturing
companies. Media agencies run on **projects, campaigns, deliverables, time, retainers, and
scopes**. Vellox ERP Next adapts ERPNext to that workflow so a studio like Vellox can run
sales → scoping → production → delivery → billing in one system, and the whole ecosystem can
use it free.

### Principles
1. **Agency-first**: campaign/client/project/timesheet as the core, not warehouses/stock.
2. **Custom Frappe app** on top of a standard ERPNext install (not a fork) — stays upgradeable.
3. **Open source**: everything we write lives in this repo as a Frappe app; docs are public.
4. **Vellox-driven**: the first paying user is Vellox Studio; roadmap follows its operations.

---

## 2. Tech Stack

| Layer      | Choice                                   | Why |
|------------|------------------------------------------|-----|
| Framework  | Frappe v15 (ERPNext v15)                 | Mature, Python/JS, bench, REST API, desk UI |
| Database   | MariaDB 10.6+                            | Frappe default |
| Cache/Queue| Redis                                     | Frappe scheduler + realtime |
| Frontend   | Frappe Desk (built-in) + custom forms     | Zero-friction admin UI |
| Client portal | Frappe portal (web pages)              | Client self-service, branded to Vellox |
| Dev tool   | Frappe Bench                             | Sites, apps, migrations, backup |
| Hosting    | Docker (docker-compose / frappe_docker)  | Reproducible, one-command deploy |

---

## 3. Modules (MVP)

Custom Frappe app: `vellox_agency`

| Module | DocTypes | Description |
|--------|----------|-------------|
| **Clients & Projects** | `Client Account`, `Engagement`, `Agency Project`, `Scope Item`, `Deliverable`, `Project Member` | Client records, retainer/one-off engagements, projects with scope, deliverables with status |
| **Campaign & Media Buying** | `Agency Campaign`, `Ad Platform Account`, `Media Spend`, `Placement` | Track campaigns, platform accounts (Meta/Google/TikTok), media plans, actual spend vs budget |
| **Content Production** | `Production Job`, `Production Task`, `Production Asset`, `Revision`, `Approval Request` | Photo/video/design jobs, task pipelines, asset versioning, client approvals |
| **Invoicing & Billing** | `Agency Invoice`, `Invoice Line`, `Retainer`, `Expense` | Retainers, line-item invoices with computed totals, expenses, payment status |
| **Timesheets & Resource** | `Agency Timesheet`, `Timesheet Entry`, `Capacity Plan`, `Skill`, `Skill Employee` | Time tracking against projects, capacity, skills, workload |
| **Reports & Dashboard** | 5 script reports: `Agency KPI`, `Budget vs Actual`, `Agency Utilization`, `Production Pipeline`, `Invoice Register`; `Vellox Agency` workspace page | Real-time dashboards per client, project, team |

### Reused from ERPNext core (no custom code)
- CRM (Lead/Opportunity), Quotations, Purchase (vendor media/stock), HR & Payroll
  (optional), Accounts (GL, payments), Help Desk (Support), Email/Calendar.

---

## 4. Milestones

| # | Milestone | Scope | Est. |
|---|-----------|-------|------|
| M0 | **Foundation** | Repo rename + README + license + CI + GitHub org/publication | 1 wk |
| M1 | **Local env** | MariaDB/Redis/bench install, Frappe+ERPNext site, Vellox brand theme | 1 wk |
| M2 | **Core CRM + Projects** | Client Account, Engagement, Project, Deliverable + desk UI + permissions | 2 wks |
| M3 | **Timesheets + Billing** | Agency Timesheet, Capacity, Agency Invoice, Retainer, Expense | 2 wks |
| M4 | **Campaigns + Production** | Campaign/Media Spend, Production Job/Asset/Approval | 2 wks |
| M5 | **Reports + Dashboard** | Project P&L, Budget vs Actual, Utilization, KPI dashboard | 1 wk |
| M6 | **Client Portal** | Branded portal, approvals, invoice view, statement | 2 wks |
| M7 | **Docker deploy + MVP release** | docker-compose, seed demo data, docs, first public release | 1 wk |

**Total: ~12 weeks to public MVP.**

---

## 5. Repo Layout

Decision (2026-08-25): the repository root **is** the installable Frappe app.
`bench get-app https://github.com/bhamalawi-alt/vellox-erp` works directly
because `pyproject.toml` and the `vellox_agency` package sit at the root.

```
vellox-erp/                     # repository root = installable Frappe app
├── vellox_agency/              # Python package: DocTypes, reports, workspace, setup
├── docs/                       # project plan, audits, specs, implementation plans
├── scripts/                    # clean-install verification and bootstrap scripts
├── pyproject.toml              # packaging metadata (flit_core)
├── LICENSE                     # MIT
└── README.md                   # public-facing install + feature docs
```

> ERPNext/Frappe itself stays a standard pip dependency (via bench), so we never fork the core.

---

## 6. Open Source & Branding

- **MIT license** — businesses can use, modify, and sell services around it.
- **Name**: "Vellox ERP Next" — keep ERPNext naming convention to signal the base.
- **Brand**: Vellox Studio wordmark + a simple studio-appropriate theme on the desk
  (logo in the login page, favicon, primary color).
- **Attribution**: README credits Frappe/ERPNext; "Built for Vellox Studio, open for all."

---

## 7. Risks

| Risk | Mitigation |
|------|-----------|
| Frappe version churn (v15 → v16) | Pin versions in docker, track upstream releases |
| MariaDB/Redis not installed here | Install via apt per bench docs (allowed unattended) |
| ERPNext bloat vs agency lean | Our app defines agency DocTypes; disable unused modules |
| Client portal branding effort | Start with desk-only in MVP; portal in M6 |
| Resource limits (8GB RAM) | Run single-site local env; use containers for prod |

---

## 8. Immediate Next Steps (M0/M1)

1. Keep repository metadata and documentation aligned with `bhamalawi-alt/vellox-erp`.
2. Write `README.md` + `LICENSE` (MIT) + `.gitignore`.
3. Install Frappe prerequisites: MariaDB 10.6, Redis, wkhtmltopdf, `bench` via pip.
4. `bench init`, create site `vellox.localhost`, install ERPNext + create `vellox_agency` app.
5. Commit everything to the renamed repo.
