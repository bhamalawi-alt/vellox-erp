# Vellox Lead-to-Project Operating Model — Design

**Card:** [P2-16] · **Date:** 2026-08-25 · **Status:** approved (owner standing
authorization recorded on card)
**Predecessors:** deep-audit target flows 1–3; Offer Builder design (2026-08-14)

## 1. Purpose and boundaries

Define one controlled path from website inquiry to an accepted, budgeted
ERPNext Project without duplicate entry:

```
Website form → Lead → Opportunity → margin-aware Quotation → accepted Project
```

ERPNext remains authoritative: **Lead, Opportunity, Quotation, Customer,
Contact, Address, Item, Item Price, Project, Task**. Vellox adds only:
a secured intake endpoint, service-package metadata on Quotation lines,
an estimate/margin panel computed from standard fields, and the acceptance
mapper that creates a Project from an approved Quotation. No parallel CRM,
estimate, or project ledgers are introduced.

## 2. Website intake

### Endpoint

`/api/method/vellox_agency.api.intake.submit_inquiry` (whitelisted,
`allow_guest=True`, POST only).

### Request fields

| Field | Required | Validation |
|---|---|---|
| full_name | yes | 2–140 chars |
| email | yes | email format; normalized lowercase |
| phone | no | free text ≤ 40 |
| company | no | ≤ 140 |
| services | yes | array ⊆ seven practice item_codes from `setup.commercial.PRACTICES` |
| message | yes | 10–5000 chars |
| consent | yes | must be true |
| website_url (hidden honeypot) | must be EMPTY | filled ⇒ silently accept + discard |

### Spam protection and idempotency

1. Honeypot field (never rendered visibly) — bot submissions return HTTP 200
   but create nothing.
2. Rate limit: per-IP token bucket via Redis (`vellox_intake:<ip>`), max 5/hour.
3. Idempotency: SHA-256 of (email, company, message, sorted services) stored in
   a `Vellox Intake Log` child-free single-purpose DocType **replaced by**
   standard **Error Log? no — by Lead dedup rule**: before insert, match existing
   open Lead with same `lead_name+email` created within 24 h → update that Lead's
   notes instead of creating a duplicate; response still 200 with lead name.

### Consent and privacy

Consent flag + timestamp + source URL stored on the Lead (custom fields
`custom_vellox_consent`, `custom_vellox_source_url`). Message body is stored in
Lead description; phone/email only in standard fields. No third-party trackers.

### Response

Always JSON `{ok:true, lead:<name>}` (200). Validation failures: 400 with
field-level messages. Server errors: 500 via standard handler — guest never
sees tracebacks.

## 3. Lead assignment, SLA, qualification

- **Assignment:** round-robin among users holding role `Vellox Sales`
  (Assignment Rule `Vellox Intake Assignment`, standard DocType).
- **First-response SLA:** custom field `custom_vellox_first_response_due`
  = creation + 4 business hours, set on validate. A standard Notification
  (`Vellox Lead First Response Due`) emails the owner daily for open Leads past
  due. Closing response = any Comment by assignee or status ≠ Open.
- **Qualification:** standard Lead status flow Open → Qualified → converted.
  Custom checkbox `custom_vellox_qualified` set during qualification review;
  conversion to Opportunity requires it true (server-side check in
  `before_convert` hook wrapper).
- **Loss reasons:** standard Opportunity `lost_reason` grouped per audit
  categories (No budget / No authority / No need / Timing / Chose competitor /
  Other) configured via fixtures.

## 4. Service package, estimate, margin model

The Offer Builder already puts services on Quotation lines. This phase adds
**planning metadata**, not new money math:

### Custom fields on Quotation (owned by vellox_agency)

| Field | Type | Purpose |
|---|---|---|
| custom_vellox_estimate_hours | Small Text | JSON list `{role, hours, rate}` per line-group |
| custom_vellox_vendor_cost | Currency | external production/vendor cost (company currency) |
| custom_vellox_estimated_margin | Percent | read-only, computed |

### Margin computation

```
revenue      = quotation.net_total (authoritative)
labor_cost   = Σ(hours × role_rate)          # rates from Employee cost-rate table [P4-31]; until then manual entries
vendor_cost  = custom_vellox_vendor_cost
margin_pct   = (revenue − labor_cost − vendor_cost) / revenue × 100
```

Computed server-side on `validate` and on demand; never writes to ERPNext
financial fields. Stored percent is informational for approval gates.

## 5. Discount and margin approval thresholds

Standard Workflow `Vellox Commercial Approval` on Quotation (draft state):

| Condition | Route |
|---|---|
| discount ≤ 5% AND estimated margin ≥ 40% | auto-approve (skip review state) |
| discount ≤ 15% AND margin ≥ 25% | `Vellox Operations` approves |
| otherwise | `Vellox Manager` (Agency Manager) approves |

Approval action recorded in Workflow Actions (standard audit). Submitting a
Quotation outside policy is impossible because Submit state is reachable only
from Approved.

## 6. Acceptance mapping — Quotation → Project

Trigger: Quotation docstatus = 1 AND standard button **Create Project**
(custom, server method `create_project_from_quotation`) visible to
Vellox Project Manager / Agency Manager.

Mapping:

| Source | Target |
|---|---|
| Quotation.customer | Project.customer |
| Quotation.name (+ amended ref) | Project.custom_vellox_quotation (Link) |
| Each Quotation Item | one Project Task group named after Item; est. hours from estimate JSON distributed across tasks |
| Project Template (Item.custom_vellox_project_template) if set | copied as task template before generated tasks |
| Estimated margin snapshot | Project.custom_vellox_expected_margin_percent (frozen at acceptance) |

Rules:
- Idempotent: second call returns the existing linked Project (409-free, same name).
- Only submitted (docstatus 1) quotations can spawn Projects; cancelled cannot.
- Project creation uses standard `frappe.new_doc("Project")`; no GL impact.
- Revenue/cost dimensions: Project set as accounting dimension on later Sales
  Invoices/Timesheets by ERPNext natively.

## 7. Permissions

| Object | Vellox Sales | Vellox Ops | Agency Manager | Agency Client |
|---|---|---|---|---|
| Lead (own-assigned) | r/w | r | r/w | — |
| Opportunity | r/w | r/w | r/w | — |
| Quotation draft | create/edit own | read | full | — |
| Margin fields | hidden (read-only after approval) | edit | edit | — |
| Create Project action | — | — | ✓ (+ Vellox PM) | — |
| Portal visibility | — | — | — | none this phase ([P6-*]) |

Enforced via standard Role Permissions + User Permissions (owner-based for
Sales), plus `has_permission` hooks where owner-scoping needs code. Guests can
ONLY reach the intake endpoint.

## 8. Audit trail

- Standard Version tracking on Lead/Opportunity/Quotation/Project (track_changes=1 on all custom fields' parents).
- Intake dedup decisions logged to `vellox_intake` logger.
- Workflow actions provide commercial approval history.
- `custom_vellox_quotation` Link preserves offer→project lineage incl. amendments (standard `amended_from`).

## 9. Notifications

1. New inquiry → welcome ack email to prospect (standard Notification, Email
   Template `Vellox Inquiry Acknowledgement`).
2. Assignment → in-app + email to assigned sales user.
3. First-response overdue → daily digest to ops.
4. Quotation approved → notify sales owner.
5. Project created → notify assigned PM.

All notifications are standard Notification records shipped as fixtures;
no custom mailer code. Failure of email never blocks the transaction
(standard background send).

## 10. Error handling summary

| Failure | Behavior |
|---|---|
| Invalid intake payload | 400, field messages |
| Honeypot hit | 200, discarded |
| Rate-limited | 429 with Retry-After |
| Duplicate within 24 h | merge into existing Lead, 200 |
| Qualification missing at convert | blocked with actionable message |
| Approval workflow bypass attempt | submit blocked by workflow state |
| Double project creation | returns existing project |

## 11. Test plan (implementation cards)

1. Intake: happy path; validation; honeypot; rate-limit; idempotent duplicate;
   consent persisted; guest cannot reach other endpoints.
2. Assignment + SLA dates set; overdue detection unit test.
3. Qualification gate blocks unqualified conversion.
4. Margin computation golden cases (EGP/USD); approval routing table cases.
5. Acceptance mapper: creates Project once; idempotent second call; template
   tasks copied; amendment lineage.
6. Permission matrix incl. cross-sales isolation.
7. All previous suite remains green (regression).

## 12. Out of scope (this phase)

Client portal exposure, retainer contracts, capacity planning, invoicing
automation, AI scoring, multi-language intake, e-signature.
