# Team Capacity and Project Profit — Design

**Card:** [P4-29] · **Date:** 2026-11-01 · **Status:** approved by the owner, 2026-11-01
**Unblocks:** [P4-102] Frappe HR · [P4-30] staff calendars · [P4-31] roles and rates ·
[P4-32] bookings and overbooking · [P4-33] budget, forecast and profit
**Builds on:** Lead-to-Project design (practice templates, estimate panel, frozen
expected margin), access by job ([P3-140]), money data for Finance and the
Agency Manager only ([P3-142])

## 1. Purpose and owner decisions

One auditable model for who is available, who is booked on what, how busy the
team is, and what each project really earns. Standard ERPNext and Frappe HR
records are the source of truth; Vellox adds only what they lack.

Owner decisions (2026-11-01):

| # | Question | Decision |
|---|---|---|
| D1 | Who does delivery work | Employees **and** freelancers, both recorded in Frappe HR (HRMS) with working days, holidays and leave |
| D2 | Cost per hour | **Finance sets it per person**; a default per role fills gaps |
| D3 | How clients pay | **Mostly fixed price.** A rate card per role is used to estimate and to measure profit, not to invoice |
| D4 | Utilization target | **75 %** billable, the same for everyone unless changed per person |
| D5 | Deals not yet won | Shown as a **separate "likely" line**, never mixed into confirmed numbers |
| D6 | Office overhead | **Left out** of project profit (contribution margin) |
| D7 | Currency | **USD**, each amount converted at the exchange rate **of its own date** (the book currency itself stays open on [P5A-103]) |
| D8 | Forecasting overruns | **Cost so far + PM's estimate of remaining hours**, updated weekly |

## 2. Records (sources of truth)

| Concept | Record | Vellox addition |
|---|---|---|
| Person (employee or freelancer) | **Employee**. Freelancers get Employment Type "Contract" (a field Frappe HR adds; to check once HRMS is installed in P4-102) | `custom_vellox_daily_hours` (default 8), `custom_vellox_utilization_target` (default 75), `custom_vellox_seniority` (Junior / Mid / Senior) |
| Delivery role | ERPNext **Designation** on the Employee; the same names as the practice-step `default_role` (Designer, Developer, Strategist, …) | none |
| Skills | HRMS **Employee Skill Map** (Skill + proficiency) | none; replaces the prototype `Skill` / `Skill Employee` DocTypes |
| Working days | **Holiday List** on the Employee, else on the Company | none |
| Leave | HRMS **Leave Application**, status Approved, including half days | none |
| Cost and bill rate | ERPNext **Activity Cost** (Employee × Activity Type: `costing_rate`, `billing_rate`); **Activity Type** default rates = the per-role default | Activity Types named after delivery roles |
| Rate history | **Timesheet** rows keep the rate in force when the time was logged | none; changing a rate never rewrites history |
| Time | ERPNext **Timesheet** (submitted only), linked to Project and Task | none |
| Confirmed booking | new **Vellox Resource Allocation** (submittable): Employee, Project, optional Task, from date, to date, hours per week | the only new DocType |
| Contract value | submitted **Quotation** behind the Project, plus submitted amendment quotations from approved Change Requests | already linked (`custom_vellox_quotation`, change control) |
| External cost | **Purchase Invoice** and **Expense Claim** lines with the Project set | none |
| Estimate | the Quotation's estimate panel (hours, rates, vendor cost) and the frozen expected margin on the Project | none |
| Remaining estimate | `custom_vellox_remaining_hours` on **Task**, updated weekly by the PM | new field |

This supersedes two parts of the older card texts:
- P4-31's custom "Vellox Rate" and "Vellox Role Profile" records are replaced by
  standard Activity Cost, Designation and Employee fields (D2). Seniority and
  target live on the Employee.
- P4-32's tentative allocations against an Opportunity are replaced by the
  computed "likely" line (D5). Only confirmed bookings are stored.

## 3. Capacity

For each person and week (Monday–Sunday):

```
working days      = days in the week − holidays (Holiday List) − approved leave days
                    (half-day leave counts 0.5)
available hours   = working days × daily hours
target hours      = available hours × utilization target / 100
confirmed hours   = Σ allocation hours/week for allocations overlapping the week;
                    a partial week counts the share of that week's working days
                    it covers (owner, 2026-11-01). Weeks run Monday to Sunday
                    (owner, 2026-11-01). Leave does not reduce booked hours.
free hours        = available hours − confirmed hours
overbooked hours  = max(0, confirmed hours − available hours)
```

- A person is **overbooked** when confirmed hours > available hours. Saving a
  booking that causes this warns; it does not block, because managers may
  overbook on purpose.
- Freelancers use the same calculation with their own daily hours and Holiday List.

### Likely demand (separate line, D5)

For each open Opportunity with an expected close date:

```
role hours  = Σ over the opportunity's service items:
                practice template steps of that role × est_days × 8
likely hours (role, week) = role hours × win probability (stage %)
                            spread evenly over the template's total duration,
                            starting at the expected close date
```

Likely demand is shown **by role**, not by person, next to confirmed numbers
("Developers: 120 h free, 60 h likely"). It never counts as overbooking. Template
steps without a role count as "Unassigned". Sales sees it in its own report
(*Vellox Likely Demand*), with no people or bookings ([P4-32]).

## 4. Utilization (actual)

```
billable hours    = submitted timesheet hours on client projects
utilization %     = billable hours ÷ available hours × 100
against target    = utilization % − utilization target
```

Internal work (projects marked internal, sales support) counts as hours worked
but not billable.

## 5. Project profit

All amounts in USD at each document's own date (D7). Overhead is excluded (D6).

```
contract value     = Σ submitted quotation net totals for the project
                     (original + approved change-request amendments)
time cost to date  = Σ submitted timesheet rows: hours × costing rate in force
external cost      = Σ Purchase Invoice and Expense Claim amounts for the project
cost to date       = time cost to date + external cost

remaining cost     = Σ open tasks: remaining hours × the assignee's cost rate
                     (role default if unassigned)
                     + quoted vendor cost not yet invoiced
forecast final cost (EAC) = cost to date + remaining cost

budget             = the quote's estimate: hours × rates + vendor cost
budget used %      = cost to date ÷ budget × 100
expected margin %  = (contract value − EAC) ÷ contract value × 100
margin drift       = expected margin % − frozen expected margin % (from the quote)
```

Health signal on the project (owner-approved thresholds):
- **Amber**: margin drift worse than −10 points, or expected margin under 25 %.
- **Red**: expected margin under 10 %, or EAC above contract value.

Invoiced revenue (from Sales Invoices) is shown beside contract value once
billing exists (P5); profit uses contract value until then.

## 6. Forecast, committed and actual stay apart

Every report labels its numbers **Actual** (submitted timesheets and invoices),
**Confirmed** (bookings and the remaining-hours estimate) or **Likely**
(pipeline). They are never summed into one figure. Every figure links to the
documents behind it.

## 7. Who sees what

Extends access by job ([P3-140], [P3-142]):

| Data | Agency Manager | Finance | Project Manager | Operations | Team member / staff | Sales |
|---|---|---|---|---|---|---|
| Availability, bookings, hours | all | all | all | all | own only | none |
| Likely demand by role | yes | yes | yes | yes | no | yes |
| Cost rates, salaries, cost and profit amounts | yes | yes | **no** | **no** | no | no |
| Budget used %, margin drift and health colour (no amounts) | yes | yes | own projects | yes | no | no |

Activity Cost moves from Project Manager / Operations edit access to Finance
and the Agency Manager only (owner, 2026-11-01), so PMs manage by hours and
percentages, not money.

Built in [P4-31]: for other jobs, timesheet rates always come from Activity
Cost (a new or changed row is looked up again; an unchanged row keeps its saved
rate). Finance views timesheets but does not edit them, so a one-off special
rate on a timesheet row is set by the Agency Manager.

## 8. Worked example

Project "Web build" (fixed price), quoted at USD 12,000.
Budget from the quote's estimate panel:

| Line | Hours × rate | USD |
|---|---|---|
| Developer | 120 h × 30 | 3,600 |
| Designer | 40 h × 25 | 1,000 |
| PM / QA | 80 h × 32.50 | 2,600 |
| Vendor (hosting, plugins) | | 600 |
| **Budget** | | **7,800** |

Frozen expected margin = (12,000 − 7,800) / 12,000 = **35 %**.

After four weeks:
- Timesheets: Developer 90 h × 30 = 2,700; Designer 35 h × 25 = 875;
  PM/QA 50 h × 32.50 = 1,625 → time cost 5,200.
- Vendor invoices: 450. Cost to date = 5,650. Budget used = 5,650 / 7,800 = 72 %.
- Remaining (PM estimate): Developer 50 h → 1,500; PM/QA 30 h → 975;
  vendor still to come 150 → remaining cost 2,625.
- EAC = 5,650 + 2,625 = 8,275. Expected margin = (12,000 − 8,275) / 12,000 = 31 %.
- Margin drift = 31 − 35 = −4 points → green (amber starts below −10 points or 25 % margin).

Capacity, the same week, Developer "Sara": 5 working days − 1 day leave = 4 ×
8 h = 32 h available; target 24 h; booked 30 h on Web build + 8 h elsewhere =
38 h → overbooked by 6 h (warning). Likely line: an Opportunity for an
eCommerce build at 60 % with 160 Developer hours over 8 weeks adds
160 × 0.6 / 8 = 12 likely Developer hours per week, shown separately.

## 9. Implementation plan (cards)

1. **[P4-102] Frappe HR**: install HRMS everywhere and make it a required app; CI installs it.
2. **[P4-30] People and calendars**: Employee fields (daily hours, target,
   seniority), Holiday Lists, Leave Applications, freelancers as Contract
   employees; the capacity calculation of §3 with tests (holidays, half-day leave).
3. **[P4-31] Roles and rates**: Designations matching practice-step roles;
   Activity Types per role with default rates; Activity Cost per person;
   Employee Skill Map; access per §7; retire prototype Skill / Capacity Plan DocTypes.
4. **[P4-32] Bookings**: Vellox Resource Allocation, overbooking warning, the
   weekly capacity view (confirmed and free), and the likely line of §3.
5. **[P4-33] Budget, forecast and profit**: Task remaining hours, the formulas of §5
   in USD per D7, health signal, utilization report (§4), drill-down to documents.

Each card is test-first, with the worked example of §8 as a regression test
where it applies.

## 10. Owner answers to the open points (2026-11-01)

1. **Health thresholds**: as proposed in §5 (amber below −10 points drift or
   25 % margin; red below 10 % margin or EAC over contract value).
2. **Money for PMs and Operations**: hidden. They see hours, budget used %,
   margin drift in points and the health colour, never amounts or rates.

### Answers after [P4-33] (owner, 2026-11-01, built in [P4-35])

3. **Billable hours**: hours on any project not marked **Internal Project**
   (a checkbox on Project) are billable. ERPNext's *Is Billable* tick on the
   timesheet row is not used, so staff do not need to remember it. Timesheet
   rows without a project are not billable.
4. **Change requests that count**: Approved and Implemented requests add their
   amendment quote to contract value and budget, and so does a Closed request
   that was implemented first (Implemented → Closed is the normal end of a
   finished change). A request closed straight from Approved was withdrawn and
   does not count. Each request records *Implemented On* when it is marked
   Implemented; a patch fills it for older requests from their change history.
5. **Remaining Hours on tasks**: everyone who sees the task reads it; only
   Project Managers, Operations and the Agency Manager change it, because it
   feeds the forecast. A change by anyone else is ignored on save.
7. **Internal Project checkbox**: anyone who edits a project (Project
   Managers, Operations, the Agency Manager) may tick it; changes are kept in
   the project's history.
6. **Accepted limit**: Project Managers can see quotes (net total and the
   estimate panel), so with budget used % and margin drift they could work out
   cost to date and the forecast cost by hand. This follows from the access in
   section 7 and is accepted; they never see the amounts directly.

### Answers for [P4-34] (owner, 2026-11-01)

8. **Quote estimate panel** (hours with rates, vendor cost, estimated margin):
   hidden from Project Managers. Sales, Operations (who approve quotes by
   margin), Finance and the Agency Manager keep it.
9. **Filtering on hidden fields**: refused. Lists, counts, single values,
   sidebar stats and searches (desk and REST) that filter on a field the
   person cannot read return a permission error, so a hidden amount cannot be
   narrowed down by repeated questions. The same applies to a hidden field
   named inside a formula in the requested columns, and every route that sends
   a document back returns only the fields the person may read.

### Answers for [P3-143] (owner, 2026-11-01)

10. **Quote labour cost**: hours are priced at the default cost rate Finance
    sets on each role's Activity Type; rates typed into the estimate are
    ignored. A quote with no estimate (no priced hours, no vendor cost) needs at
    least Operations approval.
11. **A role with no rate yet**: the draft still saves, with the margin shown
    as unknown and the role named; approving and submitting wait until Finance
    sets the rate. Each migrate lists the delivery roles still without a rate.
12. **Rate privacy**: Sales and Operations see the margin as a band and the
    approval tier, not the exact margin, which would let anyone who edits hours
    work out each role's rate. The exact margin, the labour cost and the margin
    frozen on a project are for Finance and the Agency Manager.
13. **Accepted limit (owner, 2026-11-01)**: a determined Sales or Operations
    user can still find a role's rate by re-saving a test quote about twenty
    times while watching the band flip. Operations can also infer rates from
    how margin drift moves when task hours change. Both need deliberate,
    repeated effort and are accepted.
