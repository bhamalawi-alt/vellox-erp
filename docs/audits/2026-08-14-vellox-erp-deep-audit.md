# Vellox ERP Deep Audit and Competitive Gap Analysis

**Audit date:** 2026-08-14
**Target business:** Vellox Studio
**Repository:** `bhamalawi-alt/vellox-erp`
**Runtime reviewed:** Frappe 15.118.0, ERPNext 15.119.1, `vellox_agency` 0.0.1

## Executive conclusion

The current system is an early metadata prototype, not an operational ERP. It installs 24 custom DocTypes and five reports, but it does not connect Vellox's website intake, sales pipeline, estimates, projects, timesheets, expenses, invoices, payments, or client approvals into a controlled end-to-end flow.

The correct product category is an **ERPNext-backed professional services automation (PSA) system**. ERPNext should remain the source of truth for customers, projects, employees, timesheets, accounting transactions, payments, and the general ledger. Vellox should add only the studio-specific layers needed for briefs, service packages, delivery templates, deliverables, revisions, approvals, retainers, and portfolio visibility.

The highest-risk issue is duplication. The prototype creates parallel `Client Account`, `Agency Project`, `Agency Timesheet`, `Expense`, and `Agency Invoice` records instead of using the standard ERPNext records that already own permissions, submission, accounting, tax, currency, and audit behavior. Continuing with this model would require permanent synchronization and reconciliation logic.

## Facts about Vellox Studio's operating model

The public website positions Vellox as a business development studio founded in 2019, operating remotely across the EU and MENA. It publishes seven practices:

1. Brand Strategy
2. Brand Identity
3. User Experience Design
4. Visual Content
5. Web Development
6. eCommerce
7. Web & Mobile Applications

The published delivery descriptions imply several distinct operating models:

- Brand Strategy: 4–6 week engagements with discovery, research, workshop, and strategy-document stages.
- Brand Identity: 6–10 week engagements with exploration, refinement, system design, and brand-book delivery.
- UX: 4–12 week engagements with research, information architecture, high-fidelity design, and engineering handoff.
- Visual Content: pre-production, crew/vendor coordination, shoot execution, post-production, and multi-format asset delivery.
- Web Development: architecture, weekly incremental delivery, launch, and ongoing maintenance retainers.
- eCommerce: project delivery plus migrations, post-launch support, and recurring CRO programs.
- Web and Mobile Applications: product strategy, design/build, store submission or launch, and ongoing releases.

These facts require the ERP to support fixed-fee, milestone, time-and-materials, and recurring-retainer work; internal and external costs; skill/capacity planning; revision and approval cycles; and project profitability.

The website's contact form captures name, email, phone, company, project description, and selected services. The repository contains no website integration endpoint, webhook, lead mapper, or intake automation. The audited ERP site contains zero Leads, Opportunities, and Quotations.

## Similar systems reviewed

The comparison uses official product and help documentation. It is a capability benchmark, not a vendor ranking.

### Productive

Productive connects services, budgets, resource bookings, time, expenses, invoices, profitability, and client collaboration. A service is the bridge between work planning, time tracking, and billing. Budgets support fixed, time-and-materials, non-billable, and percentage billing, with forecasted budget burn and margin. Client users can see controlled project areas without seeing internal financials.

### Scoro

Scoro connects CRM, matrix-style quoting, project planning, resource capacity, time, retainers, cost management, invoicing, and reporting. Its strongest benchmark for Vellox is quote-to-project continuity: role/effort estimates and expected margin are carried into delivery instead of being re-entered.

### Kantata

Kantata emphasizes demand forecasting, skill-based staffing, estimate scenarios, project budgets, actual versus forecast cost, margin protection, billing automation, revenue recognition, and portfolio intelligence. Its benchmark value is forward-looking capacity and financial control rather than task management alone.

### Teamwork

Teamwork focuses on client work with quote-to-project conversion, project budgets, budget thresholds, cost and billable rates, native time tracking, multi-currency handling, capacity/utilization, project health, and profitability reporting.

### Accelo

Accelo connects contacts, sales, project templates, retainers, scheduling, time, expenses, invoicing, tickets, client communications, and automated triggers. Its useful benchmark for Vellox is recurring client work and operational automation.

## Competitive capability matrix

| Capability | Mature PSA pattern | Current Vellox state | Gap |
|---|---|---|---|
| Website intake | Form creates a lead, activity, owner, SLA, and follow-up | No integration code; 0 Leads | Blocker |
| CRM pipeline | Lead → qualified opportunity → quote, with probability and next action | ERPNext is installed but unused; custom `Engagement` duplicates part of the lifecycle | Blocker |
| Service catalogue | Services carry pricing, cost assumptions, delivery templates, and reporting category | No Vellox service catalogue; only 10 stock-item demo records | Blocker |
| Scoping and estimating | Deliverables, roles, effort, vendor cost, margin, and scenarios before approval | No estimate model or quote extension | Blocker |
| Quote-to-project handoff | Accepted estimate creates the project, budget, phases, tasks, and staffing demand | No mapper, hook, button, or automation | Blocker |
| Project delivery | Templates, milestones, dependencies, baseline, health, risks, change control | `Agency Project` is a 17-field parallel record with no lifecycle logic | Critical |
| Deliverables | Deliverable owner, due date, files, versions, acceptance criteria, revision allowance, approval history | Basic status fields only; no enforced links or approval workflow | Critical |
| Capacity planning | Employee calendars, leave, skills, tentative demand, allocations, utilization targets | Manual `Capacity Plan` totals linked to `User`; no calendars or demand forecast | Critical |
| Time control | Employee/activity/project entries, approval, locking, billable rate, invoice status | Custom timesheet totals only; not submittable; no workflow | Critical |
| Expense/procurement | Supplier/employee expense, receipt, approval, project/cost center, billable flag, accounting entry | Parallel `Expense`; no GL impact; `Expense Claim` table is absent | Critical |
| Fixed/T&M/milestone billing | Billing rules originate in the approved commercial scope | No billing-rule engine | Critical |
| Retainers | Recurrence, included allowance, usage, rollover, overage, renewal, auto-invoice | `Retainer` stores dates and amount only | Critical |
| Accounting and collections | Submitted invoice → ledger → payment → reconciliation → aging | ERPNext works in demo data, but Vellox reports read non-accounting `Agency Invoice` | Blocker |
| Profitability | Revenue, labor cost, external cost, overhead, EAC, margin by client/project/service | No reliable project P&L or forecast | Blocker |
| Client portal | Client-specific projects, files, approvals, invoices, statements, comments | `Agency Client` role exists but has no permissions or portal UI | Critical |
| Automation | Assignment, reminders, overdue escalation, budget alerts, renewal notices | 0 Workflows, Assignment Rules, Client Scripts, Server Scripts, or Vellox Notifications | Critical |
| Reporting | Role-sensitive actual/forecast financial and operational dashboards | Five empty custom-data reports; no report filter JavaScript | Critical |
| Security | Least privilege, record-level client/team scope, separate financial visibility | Broad staff export/share permissions; no owner or record restrictions | Blocker |
| Auditability | Submission, amendment, workflow history, change tracking | 0 custom DocTypes are submittable; 0 track changes | Blocker |
| Quality and releases | Automated migrations, unit/integration tests, CI, reproducible deployment | 0 tests; no CI or deploy definition; app packaging is inconsistent | Blocker |

## Current repository and runtime evidence

### Installed application structure

- 24 custom DocTypes: 14 main records and 10 child tables.
- 22 of the 24 Python controllers contain only `pass`.
- Only `Agency Invoice` and `Agency Timesheet` calculate basic totals.
- No JavaScript files, automated tests, Vellox workflows, Vellox notifications, Vellox web forms, portal pages, webhooks, or assignment rules.
- `hooks.py` does not declare ERPNext as a required app and contains no active integration, permission, scheduler, or fixture configuration beyond the install hook.
- The app is nested under `apps/vellox_agency`, while the repository root is not a directly installable Frappe app. The documented `bench get-app` flow therefore does not match the repository packaging.

### Live-site state

- Installed apps: Frappe 15.118.0, ERPNext 15.119.1, Vellox Agency 0.0.1.
- Two companies exist: `Vellox Studio` and `Vellox Studio (Demo)`.
- The standard ERPNext accounting demo contains 3 Customers, 3 Suppliers, 10 stock Items, 5 submitted Sales Invoices, 6 submitted Purchase Invoices, and 5 submitted Payment Entries.
- The site contains 0 Leads, Opportunities, Quotations, Projects, Tasks, Employees, Timesheets, and Subscriptions.
- Every Vellox transactional DocType also contains 0 records.
- The demo catalogue is retail inventory such as laptops, mugs, and shoes. It does not represent Vellox services.
- A failed site directory remains under `sites/vellox.localhost.failed`; the scheduler repeatedly tries to access it and logs database authentication errors.

### Data-model findings

- `Client Account` duplicates Customer, Contact, and Address.
- `Agency Project` duplicates Project and separates project work from ERPNext profitability.
- `Agency Timesheet` links to `User`, not Employee, and bypasses standard Timesheet billing.
- `Expense` uses free-text vendor data and bypasses Supplier, Purchase Invoice, Expense Claim, and the ledger.
- `Agency Invoice` is not submittable and cannot create GL entries, receivables, tax postings, or Payment Entry reconciliation.
- No main custom DocType has a title field, change tracking, or formal submit/cancel/amend behavior.
- Managers can delete financial and operational records. Staff can export and share most records. The Agency Client role has no custom DocType permissions.

### Report and workspace defects

- All five reports execute, but return empty Vellox datasets even though standard ERPNext contains accounting data.
- `Agency KPI` labels results with an `as_of` date but does not filter any source data by that date.
- KPI totals combine currencies without conversion or company context.
- Raw SQL reports do not implement record-level permission conditions even though their Report metadata enables user permissions.
- `Production Pipeline` excludes `Done`, but Production Job does not have a `Done` status.
- Invoice and production overdue calculations return negative day values for overdue records.
- No report has a companion `.js` file, so users have no visible date, client, employee, status, or company filters.
- The public workspace has no role restrictions, number cards, or charts.
- The `New Client` shortcut filters `Client Account.status = Open`, but `Client Account` has no `status` field, producing a runtime query error.

## Scope mismatch

The repository describes the product as an ERP for a media agency and gives Campaign/Media Buying an entire module. Vellox's published service catalogue does not list media buying or paid advertising. A campaign shoot under Visual Content is a production workflow, not an ad-spend workflow.

Therefore Campaign/Media Buying should be treated as **deferred or optional** until Vellox confirms that it is an actual revenue-producing service. The immediate rebuild should prioritize the seven published practices and their common commercial/delivery lifecycle.

## Target end-to-end flows

### 1. Inquiry to qualified opportunity

Website contact submission → Lead → service interests and source → assigned owner → first-response deadline → diagnostic call → qualification → Opportunity.

### 2. Opportunity to approved scope

Opportunity → discovery brief → service package → phases/deliverables → role and hour estimates → vendor/production costs → price and margin → internal commercial approval → client Quotation/Proposal → accepted or lost.

### 3. Accepted scope to delivery plan

Accepted Quotation → Customer if needed → ERPNext Project → project budget/accounting dimensions → practice template → phases, tasks, milestones, deliverables → tentative resource demand becomes confirmed allocations → kickoff checklist.

### 4. Delivery and change control

Task/time/expense capture → budget burn and forecast → deliverable version → internal review → client review → approval/rejection → revision consumption → change request when scope, cost, or timing changes → approved commercial amendment.

### 5. Billing and collection

Billing schedule or approved time/expense → draft Sales Invoice → finance review → submit → send/payment request → Payment Entry → reconciliation → aging and collection follow-up. No parallel invoice ledger.

### 6. Retainer operation

Contract/service package → recurring Subscription or controlled invoice schedule → monthly allowance and planned capacity → work/time consumption → rollover/overage rules → client report → renewal/cancellation workflow.

### 7. Portfolio and management reporting

Pipeline-weighted demand → capacity forecast → project health → budget burn/EAC → utilization → revenue and gross margin → invoicing forecast → receivables/DSO → client and service-line profitability.

## Prioritized rebuild backlog

### P0 — Foundation and accounting integrity

1. Make the repository a correctly packaged, installable Frappe app and pin supported versions.
2. Declare ERPNext dependency, add migrations, CI, tests, backups, and clean deployment configuration.
3. Remove the failed-site scheduler target and establish separate development/test/production sites.
4. Make ERPNext Customer, Project, Employee, Timesheet, Sales Invoice, Purchase Invoice, Payment Entry, and accounting dimensions authoritative.
5. Define migration/deprecation rules for all duplicate custom records before production data exists.
6. Establish service Items, Item Groups, cost centers/accounting dimensions, currencies, taxes, terms, and Vellox print formats.
7. Establish least-privilege roles and record-level access before importing real data.

### P1 — Lead to project

1. Integrate the website contact form with a secured lead-intake endpoint.
2. Configure Lead/Opportunity qualification, assignment, response SLA, and loss reasons.
3. Build Vellox service packages and a margin-aware estimate linked to Quotation.
4. Add internal approval thresholds for discount and margin.
5. Convert accepted scope into Project, budget, phases, tasks, deliverables, and staffing demand.

### P2 — Delivery operations

1. Create templates for each published Vellox practice.
2. Implement project health, risks, dependencies, milestones, and change requests.
3. Implement Deliverable, Deliverable Version, Review Round, and Approval with enforced transitions.
4. Connect files, comments, internal versus client-visible notes, and notifications.
5. Replace custom timesheets with controlled ERPNext Timesheets and approval/locking rules.

### P3 — Capacity and profitability

1. Install/configure the appropriate HR capability for Employee, leave, holiday calendars, and expenses.
2. Define skills, roles, seniority, cost rates, bill rates, and utilization targets.
3. Build allocations using confirmed work and tentative pipeline demand.
4. Add forecasted budget burn, estimate-at-completion, utilization, and project/client/service profitability.

### P4 — Billing, retainers, and portal

1. Support fixed fee, milestone, time-and-materials, reimbursable expense, and mixed billing.
2. Implement retainer allowance, usage, rollover, overage, auto-invoicing, renewal, and pause/cancel rules.
3. Build a branded client portal for approved projects, deliverables, files, reviews, invoices, statements, and comments.
4. Keep internal cost, margin, staff notes, and unrelated client data inaccessible to portal users.

### P5 — Optional practice modules and integrations

1. Add visual-production scheduling, shot lists, crew/vendor coordination, usage rights, and asset delivery where required.
2. Add GitHub/Jira/Figma/Drive/calendar/payment integrations only after the core flows are stable.
3. Reintroduce campaign/media-spend management only if Vellox confirms it as an active service line.

## Recommended acceptance criteria for a usable first release

A release is not operational until one test client can complete this flow without duplicate entry:

1. Website inquiry creates and assigns a Lead.
2. Lead becomes an Opportunity and approved Quotation with an expected margin.
3. Acceptance creates a correctly budgeted Project with a service template and staffing plan.
4. Staff log approved time and expenses against the Project.
5. A deliverable is reviewed, revised, and approved with a complete audit trail.
6. The Project produces a submitted Sales Invoice in ERPNext.
7. Payment is recorded and reconciled.
8. Project P&L, budget burn, utilization, and receivables show correct figures in company currency.
9. The client sees only their approved portal content.
10. Automated tests repeat the flow on a clean site.

## Sources

### Vellox Studio

- https://www.velloxstudio.com/
- https://www.velloxstudio.com/services
- https://www.velloxstudio.com/contact
- https://www.velloxstudio.com/about
- The seven individual service pages under `/services/`.

### Comparable PSA systems

- Productive: https://productive.io/
- Productive budgets: https://help.productive.io/en/articles/2179575-what-is-a-budget
- Productive resource planner: https://help.productive.io/en/articles/2179625-what-is-the-resource-planner
- Productive client portal: https://productive.io/blog/create-a-client-portal-for-your-agency/
- Scoro: https://www.scoro.com/
- Kantata PSA: https://www.kantata.com/product
- Kantata project accounting: https://www.kantata.com/psa/project-management-software/project-accounting
- Teamwork product tour: https://www.teamwork.com/product/
- Accelo user guide: https://help.accelo.com/guides/user/

### ERPNext and Frappe

- Quotation: https://docs.frappe.io/erpnext/quotation
- Opportunity: https://docs.frappe.io/erpnext/opportunity
- Project: https://docs.frappe.io/erpnext/project
- Project profitability: https://docs.frappe.io/erpnext/project-profitability
- Sales Invoice and Timesheet billing: https://docs.frappe.io/erpnext/sales-invoice
- Subscription: https://docs.frappe.io/erpnext/subscription
- Users and permissions: https://docs.frappe.io/framework/user/en/basics/users-and-permissions
- Assignments and ToDos: https://docs.frappe.io/framework/assignments-and-todos
