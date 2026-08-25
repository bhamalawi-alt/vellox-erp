# Lead-to-Project Implementation Plan

> **For agentic workers:** implement task-by-task with failing-test-first per
> card. Source: approved design `docs/superpowers/specs/2026-08-25-lead-to-project-design.md`
> ([P2-16], owner standing authorization).

**Goal:** website inquiry → Lead → Opportunity → margin-aware Quotation →
accepted ERPNext Project, with no parallel ledgers.

**Stack:** Frappe v15 / ERPNext v15, Python 3.11, Frappe tests + node --test,
existing CI pipeline (full suite gate).

## Global constraints

- Standard Lead/Opportunity/Quotation/Customer/Project stay authoritative.
- All custom fields prefixed `custom_vellox_`; owned by `vellox_agency` via
  idempotent setup code in `vellox_agency/crm_setup.py` (after_migrate chain).
- Guests reach ONLY `vellox_agency.api.intake.submit_inquiry`.
- No modification of upstream apps; no new financial ledgers.
- Every behavior change ships with its failing test first.

## Local bench rule

Same as the Offer Builder plan: rsync repo root →
`/private/tmp/vellox-frappe-bench/apps/vellox_agency/` (excludes
`.git .bench-venv frappe-bench docs scripts __pycache__ *.pyc`, no `--delete`)
before every migrate/build/test command.

---

### Task 1: Intake endpoint (P2-17)

**Files:** create `vellox_agency/api/__init__.py`, `vellox_agency/api/intake.py`;
create `vellox_agency/tests/test_intake.py`; hooks `required_apps` unchanged.

- [ ] Failing tests: happy path creates Lead with services JSON, consent,
      source URL; validation 400s; honeypot discard; rate-limit 429; 24 h
      duplicate merge; guest isolation (other endpoints unreachable).
- [ ] Implement whitelist POST handler + Redis bucket + dedup query.
- [ ] Green; full suite green; commit `feat: secured website inquiry intake`.

### Task 2: Assignment, SLA and qualification (P2-18)

**Files:** fixtures for Assignment Rule + Notifications (Email Template +
Notification records); `crm_setup.py` sets `custom_vellox_first_response_due`,
qualification checkbox; convert-gate wrapper test + implementation.

- [ ] Failing: new Lead gets assignee + due date; overdue query helper;
      unqualified conversion blocked with message.
- [ ] Implement via standard records created idempotently.
- [ ] Commit `feat: lead assignment, response SLA and qualification gate`.

### Task 3: Estimate and margin panel on Quotation (P2-20)

**Files:** setup adds three custom fields; `vellox_agency/estimate.py`;
tests/test_estimate.py.

- [ ] Failing golden cases: margin math EGP+USD; hidden from Sales after
      approval; recomputed on validate; never writes financial fields.
- [ ] Implement computation + field wiring via apply_baseline.
- [ ] Commit `feat: margin-aware estimate panel on quotation`.

### Task 4: Commercial approval workflow (P2-21)

**Files:** Workflow + states fixture `Vellox Commercial Approval`; tests.

- [ ] Failing routing table cases (discount/margin matrix) incl. bypass block.
- [ ] Implement workflow fixture creation idempotently.
- [ ] Commit `feat: commercial approval thresholds on quotation`.

### Task 5: Acceptance mapper — Quotation to Project (P2-22)

**Files:** `vellox_agency/acceptance.py` whitelisted `create_project_from_quotation`;
custom link fields; tests/test_acceptance.py.

- [ ] Failing: submitted-only rule; single Project per quotation (idempotent);
      template tasks copied then generated groups per Item; amendment lineage;
      permissions (PM/Manager only).
- [ ] Implement mapper using standard Project doc.
- [ ] Commit `feat: create project from accepted quotation`.

### Task 6: Acceptance verification (P2-19 pipeline config folded here)

- [ ] Opportunity pipeline stages + loss reasons fixtures verified by test.
- [ ] Full regression + clean-install verifier green from remote branch.
- [ ] Browser-equivalent scenario scripted: intake→assign→qualify→quote→
      approve→accept→project exists with tasks and frozen margin.
- [ ] Commit `test: lead-to-project acceptance`.

---

## Rollback strategy

Each task is an independent revert. The intake endpoint is additive; removing
it restores the previous public surface. Custom fields are inert if code is
reverted. Workflow fixture removal returns Quotations to standard lifecycle.

## Definition of done

All cards Done, full suite green on master CI, verifier green from documented
URL, audit-trail checks pass, and the audit's flow-1..3 acceptance criteria
demonstrated by the Task 6 scenario.
