# Delivery, Deliverables & Change Control — Implementation Plan

> **For agentic workers:** failing-test-first per task; rsync bench rule from
> the Lead-to-Project plan applies. Source design:
> `docs/superpowers/specs/2026-08-25-delivery-change-control-design.md` ([P3-23]).

**Goal:** the four-DocType studio delivery layer on standard Project/Task with
enforced lifecycle, revision control and change management.

**Stack:** Frappe v15 / ERPNext v15 · Python 3.11 · existing CI (full suite).

## Global constraints

- Project/Task/Timesheet/Sales Invoice remain authoritative.
- All status transitions flow through `deliverable.transition()`.
- Client-visible filtering enforced server-side via
  `permission_query_conditions` from the first release.
- Price changes route exclusively through a new Quotation chain.

---

### Task 1: DocTypes + fields fixture (P3-25 part 1)

**Files:** doctype folders for the four DocTypes; `delivery_setup.py`
(fields + roles wiring into apply_baseline); tests/test_delivery_setup.py.

- [ ] Failing: fixtures exist after migrate; track_changes set; permissions match matrix §8.
- [ ] Implement JSONs + setup. Commit `feat: delivery doctypes and baseline`.

### Task 2: Deliverable lifecycle engine (P3-26 part 1)

**Files:** `vellox_agency/deliverable.py`; tests/test_deliverable_lifecycle.py.

- [ ] Failing: legal transition table green-path; every illegal move raises
      with current-state message; final approve requires client round outcome.
- [ ] Implement `transition()` state machine per design §3.1.
- [ ] Commit `feat: deliverable lifecycle state machine`.

### Task 3: Versions & review rounds (P3-26 part 2)

**Files:** child-table logic inside deliverable.py; tests/test_versions.py.

- [ ] Failing: edit-creates-version immutability; allowance exhaustion forces
      Changes-Requested + CR requirement.
- [ ] Commit `feat: deliverable versions and review rounds`.

### Task 4: Change Requests (P3-27)

**Files:** `vellox_agency/change_request.py`; tests/test_change_request.py.

- [ ] Failing: terminal-state rules; implemented-with-price requires new
      submitted quotation; schedule days adjust project end date.
- [ ] Commit `feat: change request control`.

### Task 5: Visibility & notifications (P3-27 remainder)

**Files:** hooks permission_query_conditions for the four DocTypes;
Notification fixtures; tests/test_delivery_visibility.py.

- [ ] Failing: cross-client list denial; guest denial; notification records exist.
- [ ] Commit `feat: delivery visibility and notifications`.

### Task 6: Practice templates (P3-24)

**Files:** `vellox_agency/setup/practice_templates.py` — seven Project
Templates with phases/milestone tasks/dependencies/roles from published
delivery ranges; template-edit safety test (editing template never mutates
existing Projects because tasks were copied at creation).
- [ ] Commit `feat: seven practice project templates`.

### Task 7: Phase acceptance

- [ ] Full suite green locally + CI; clean-install verifier green from remote
      URL; scripted scenario: template→project→deliverable→review→CR→amend.
- [ ] Evidence comment; phase cards to Done.
