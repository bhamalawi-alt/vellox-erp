# Vellox Project Delivery, Deliverables & Change Control — Design

**Card:** [P3-23] · **Date:** 2026-08-25 · **Status:** approved (owner standing
authorization recorded on card)
**Predecessors:** audit flow 4 + P2 backlog; Lead-to-Project design ([P2-16])

## 1. Purpose

Define the studio delivery layer that sits ON TOP of standard ERPNext Project
and Task (which remain the execution and scheduling backbone). Vellox adds
exactly four custom DocTypes plus a small set of fields:

| DocType | Kind | Purpose |
|---|---|---|
| `Vellox Deliverable` | main | client-facing output with acceptance lifecycle |
| `Vellox Deliverable Version` | child | immutable snapshot per review round |
| `Vellox Review Round` | child | internal/client review outcome log |
| `Vellox Change Request` | main | scope/price/schedule amendments |

Standard boundaries: no custom task management, no custom time tracking, no
parallel financials — Task, Timesheet, Sales Invoice stay authoritative.

## 2. Project health, phases, milestones, dependencies, risks

### Fields on Project (custom, owned by vellox_agency)

| Field | Type | Values / rule |
|---|---|---|
| custom_vellox_health | Select | `On Track` / `At Risk` / `Off Track`; default On Track |
| custom_vellox_phase | Select | `Discovery` / `Design` / `Build` / `Launch` / `Post-Launch`; auto-set by template tasks when created |
| custom_vellox_risks | Small Text | free-text risk register summary (structured register deferred) |

Rules:
- Health transitions are manual by Project Manager role only.
- Phase changes are logged via standard Version tracking.
- Milestones = standard Task with `is_milestone = 1` (ERPNext native).
- Dependencies = standard Task `depends_on` (native).

## 3. Deliverables

### 3.1 Lifecycle states

```
Draft → Internal Review → Client Review → Approved
                     ↘ Changes Requested → (new version) → Internal Review
Any pre-Approved state → Cancelled
```

Unreachable/ambiguous transitions: none. `Changes Requested` always returns to
`Internal Review` after a new version is attached. Terminal states: Approved,
Cancelled.

### 3.2 Fields

| Field | Rule |
|---|---|
| project (Link, reqd) | must be a live Project |
| title, deliverable_type (Select: Document/Design/Media/Code/Report) | reqd |
| due_date | validated ≥ project start |
| revision_allowance (Int, default 2) | max review rounds before change request required |
| current_version (read-only) | latest approved-or-pending version number |
| status | lifecycle above |
| accepted_on, accepted_by | set on approval by client-facing actor |

### 3.3 Versions & review rounds

A **Version** is an immutable child snapshot (file URL + notes + author +
timestamp). Rules:
1. Editing content creates a NEW version row; old rows never mutate.
2. Each submitted version starts one **Review Round** recording reviewer,
   audience (`Internal` / `Client`), outcome (`Approved` / `Changes Requested`),
   comments, timestamp.
3. Rounds consumed > revision_allowance ⇒ status forced to
   `Changes Requested` and a Change Request becomes REQUIRED (validation).

## 4. Internal vs client-visible content

- `client_visible` checkbox per Review Round comment and per Deliverable file note.
- Portal queries (future [P6-*]) MUST filter: `project in (client's projects)`
  AND `client_visible = 1`. Enforced by permission_query_conditions hook from
  day one (not deferred to portal phase).
- Internal costs/margins/staff notes are NEVER stored on Deliverable docs.

## 5. Approval transitions & permissions

| Action | Allowed roles |
|---|---|
| Create/edit Draft deliverable | Agency Staff, Agency Manager, Vellox Team Member |
| Submit for internal review | Vellox Team Member |
| Internal approve → Client Review | Vellox Project Manager |
| Record client outcome | Vellox Project Manager / Agency Manager |
| Approve (final) | Agency Manager or recorded client confirmation |
| Reopen via new version | original creator + PM |

All state moves go through a single server method
`vellox_agency.deliverable.transition(doc, action)` — no direct status writes
(`docstatus` stays 0; `track_changes = 1`).

## 6. Change control

### 6.1 Vellox Change Request fields

project (reqd), title, reason, affected_deliverables (multi-select),
schedule_impact_days (Int), price_impact (Currency), requires_new_quotation
(read-only computed), status:
```
Draft → Under Review → Approved → Implemented → Closed
                    ↘ Rejected ↗
```
Rejected/Implemented/Closed are terminal. Implemented is reachable ONLY when:
(a) schedule impact ⇒ Project end date adjusted (+days) AND tasks re-planned;
(b) price impact ≠ 0 ⇒ a NEW Quotation (amendment chain) is created and its
submission is required before marking Implemented.

### 6.2 Financial routing rule (hard boundary)

Price changes NEVER edit accounting documents. Flow: CR Approved (price≠0) →
system drafts amended Quotation linked via standard `amended_from` semantics →
client accepts → normal ERPNext selling flow proceeds. Invoices already
submitted remain untouched.

## 7. Files, comments, notifications, audit

- Files attach to Deliverable versions using standard File doc
  (`attached_to_doctype/name`) — ownership follows the Deliverable.
- Comments use standard Comment with `custom_vellox_client_visible` flag.
- Notifications (standard Notification records, fixtures):
  1. Deliverable sent to client review → assigned PM email.
  2. Client decision recorded → creator.
  3. CR approved/rejected → project team.
  4. Revision allowance exhausted → Agency Manager digest.
- Audit trail = track_changes on all four DocTypes + Workflow-less transition
  log rows (Review Round / status history inside Version rows).

## 8. Permission matrix

| Object | Agency Staff | Vellox Team Member | Vellox PM | Agency Manager | Agency Client* |
|---|---|---|---|---|---|
| Deliverable create/edit own | ✓ | ✓ | ✓ | ✓ | — |
| Read all in own project | — | ✓ | ✓ | ✓ | client-visible only |
| Transition submit/internal | — | ✓ | ✓ | ✓ | — |
| Final approve | — | — | ✓ | ✓ | — (portal action later) |
| Change Request create | ✓ | ✓ | ✓ | ✓ | portal later |
| CR approve | — | — | price=0 | any | — |

\* Agency Client desk access remains disabled this phase; portal arrives [P6-*]
using the query conditions defined here.

## 9. Test plan (implementation cards)

1. Deliverable lifecycle: every legal transition; each illegal transition raises.
2. Version immutability: editing creates new row; old row hash unchanged.
3. Revision allowance exhaustion forces CR requirement.
4. Lost-reason-style enforcement: client round outcome required before Approved.
5. Change Request gates: implemented-with-price blocked without new submitted
   quotation; schedule adjustment math.
6. Visibility: client_visible filter via permission_query_conditions; cross-client denial.
7. Template→Project integration still green (regression with P3-24 fixtures).
