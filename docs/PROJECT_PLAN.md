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
1. **Agency-first**: clients, quotes, projects, deliverables and time as the core, not warehouses/stock.
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
| Client portal | Frappe portal (web pages), planned     | Client self-service, branded to Vellox |
| Dev tool   | Frappe Bench                             | Sites, apps, migrations, backup |
| Hosting    | To be decided at the deployment cards    | See docs/environments.md |

---

## 3. Modules

> **Status (2026-10-31, [P3-101]).** The prototype modules first planned here
> were replaced after the 2026-08-14 audit
> ([docs/audits/2026-08-14-vellox-erp-deep-audit.md](audits/2026-08-14-vellox-erp-deep-audit.md)):
> ERPNext records are the source of truth, and the app adds the studio's rules
> around them. What works today is listed in the [README](../README.md#what-works-today).

### Built (ERPNext-backed)

| Area | ERPNext records | Vellox additions |
|---|---|---|
| Inquiries and sales | Lead, Opportunity, Quotation, Item | Website intake, reply deadlines and routing, qualification gate, stage probabilities, lost reasons, technical proposal, margin estimate, tiered approval, print formats |
| Delivery | Project, Task, Project Template | Create from quote or practice template, health, phase, project manager, risks, `Deliverable` lifecycle, `Vellox Change Request` |
| People and access | User, Role Profile | Job profiles and per-job access limits, team-member project scoping |
| Automation | Notification, scheduler | Seven alerts, hourly and daily jobs |

### Retired prototype modules

| Prototype | Status | Use instead |
|---|---|---|
| `Client Account` | **Retired**, new records blocked | Customer / Contact / Address |
| `Engagement`, `Retainer` | **Retired**, new records blocked | Quotation + Subscription |
| `Agency Project`, `Scope Item`, `Project Member` | **Retired** (`Agency Project` blocked) | Project, Task, Project User |
| `Agency Timesheet`, `Timesheet Entry` | **Retired**, new records blocked | Timesheet |
| `Agency Invoice`, `Invoice Line`, `Expense` | **Retired**, new records blocked | Sales Invoice; Expense Claim or Purchase Invoice |
| `Agency Campaign`, `Ad Platform Account`, `Media Spend`, `Placement` | **Prototype, not in use**; deferred until campaigns are confirmed as a paid service | — |
| `Production Job`, `Production Task`, `Production Asset`, `Revision`, `Approval Request` | **Prototype, not in use**; content delivery runs on `Deliverable` | Deliverable |
| `Capacity Plan`, `Skill`, `Skill Employee` | **Prototype, not in use**; replaced by the capacity plan card [P4-29] | Employee (HRMS), planned |
| Reports `Agency KPI`, `Agency Utilization`, `Budget vs Actual`, `Invoice Register`, `Production Pipeline` | **Disabled**: they read the retired or prototype DocTypes | New reports planned per phase |

Blocking and data handling for retired ledgers: [docs/migrations/deprecation-map.md](migrations/deprecation-map.md).

### Reused from ERPNext core (no custom code)
- CRM, Quotations, Purchase, Accounts (GL, payments), Projects, Timesheets,
  HR & Payroll (optional, via HRMS), Help Desk (Support), Email/Calendar.

---

## 4. Roadmap

The milestone table that used to be here (M0–M7) described the retired
prototype. The live roadmap, with every card's status, is the Trello board
**Vellox ERP Delivery**: <https://trello.com/b/6a8cd7ae5da50cd22d3356a2>.
Its phases:

| Phase | Content |
|---|---|
| P0–P2 | Foundation, CI, security baseline, lead-to-project flow (done) |
| P3 | Delivery, change control, access by job, scheduled jobs (in progress) |
| P4 | Team capacity, cost rates and project profit (planning) |
| P5 | Company books, currencies, billing and retainers |
| P6+ | Client portal, integrations, go-live |

Each card is built test-first and lands through a reviewed pull request with
green CI.

---

## 5. Repo Layout

Decision (2026-08-25): the repository root **is** the installable Frappe app.
`bench get-app https://github.com/bhamalawi-alt/vellox-erp` works directly
because `pyproject.toml` and the `vellox_agency` package sit at the root.

```
vellox-erp/                     # repository root = installable Frappe app
├── vellox_agency/              # Python package: DocTypes, reports, workspace, setup
├── docs/                       # project plan, audits, specs, implementation plans
├── scripts/                    # clean-install verification, backup, restore and deploy scripts
├── pyproject.toml              # packaging metadata (flit_core)
├── LICENSE                     # MIT
└── README.md                   # public-facing install + feature docs
```

> ERPNext/Frappe itself stays a standard pip dependency (via bench), so we never fork the core.

---

## 6. Open Source & Branding

- **MIT license** — businesses can use, modify, and sell services around it.
- **Name**: "Vellox ERP Next" — keep ERPNext naming convention to signal the base.
- **Brand** (not built yet): Vellox Studio wordmark + a simple studio-appropriate theme on the desk
  (logo in the login page, favicon, primary color).
- **Attribution**: README credits Frappe/ERPNext; "Built for Vellox Studio, open for all."

---

## 7. Risks

| Risk | Mitigation |
|------|-----------|
| Frappe version churn (v15 → v16) | Supported-range gate before every migrate; v16 only as an announced release |
| ERPNext bloat vs agency lean | Use ERPNext records; hide unused modules from each job's workspace |
| Client portal branding effort | Desk-only until the portal phase (P6) |
| Resource limits (8GB RAM) | Run single-site local env; use containers for prod |

---

## 8. Next steps

See the **01 — Ready** list on the Trello board above.
