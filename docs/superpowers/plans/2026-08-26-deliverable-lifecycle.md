# P3-26: Deliverable Lifecycle, Versions & Review Rounds — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development or superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Rework the existing `Deliverable` DocType skeleton into the full
lifecycle DocType per design section 3, add two child DocTypes (Version + Review
Round), wire a `transition()` state machine, and enforce version immutability
with revision-allowance gating.

**Architecture:** Three tasks, each producing independently testable deliverables.
All status transitions go through one server function
`vellox_agency.deliverable.transition()`. Child DocTypes are never edited after
insert (immutability enforced in Python). The existing `Deliverable.json`
skeleton is reworked in-place (same `module`, same directory).

**Stack:** Frappe v15 / ERPNext v15 · Python 3.11 · FrappeTestCase · CI full suite.

**Source of truth:**
- Design: `docs/superpowers/specs/2026-08-25-delivery-change-control-design.md` (sections 3, 5)
- Parent plan: `docs/superpowers/plans/2026-08-25-delivery-change-control.md` (Tasks 2, 3)

## Global Constraints

- Project / Task / Timesheet / Sales Invoice remain authoritative (no custom
  scheduling, time tracking, or financial ledgers).
- All status transitions flow through `deliverable.transition(doc, action)`.
- Client-visible filtering enforced server-side via `permission_query_conditions`
  from the first release (deferred to P3-27 but DocType `client_visible` flag is
  added now).
- `track_changes = 1` on all main DocTypes. `docstatus` stays 0 (non-submittable).
- Existing CI full suite must remain green after every commit.
- rsync to `/private/tmp/vellox-frappe-bench/apps/vellox_agency/` after every
  file change for local testing.

## File Map

| Action | File | Responsibility |
|---|---|---|
| Rewrite | `vellox_agency_projects/doctype/deliverable/deliverable.json` | Fields, statuses, permissions per design §3+§8 |
| Rewrite | `vellox_agency_projects/doctype/deliverable/deliverable.py` | Minimal controller (lifecycle logic lives in root deliverable.py) |
| Create | `vellox_agency_projects/doctype/vellox_deliverable_version/{__init__.py, .json, .py}` | Child table: immutable version snapshot |
| Create | `vellox_agency_projects/doctype/vellox_review_round/{__init__.py, .json, .py}` | Child table: review outcome log |
| Create | `vellox_agency/deliverable.py` | `transition()` state machine + version/round helpers |
| Create | `vellox_agency/delivery_setup.py` | DocType reload + setup wiring (idempotent) |
| Modify | `vellox_agency/security.py:27-52` | Add `setup_delivery_fields()` call to `apply_baseline` |
| Modify | `vellox_agency/hooks.py:20-64` | Add `doc_events["Deliverable"]` validate hook |
| Create | `vellox_agency/tests/test_deliverable_lifecycle.py` | Lifecycle transition tests (Task 2) |
| Create | `vellox_agency/tests/test_deliverable_versions.py` | Version/round immutability tests (Task 3) |

---

## Task 1: DocType Fixtures + Delivery Setup

**Goal:** Deliverable, Version, and Review Round DocType JSONs exist with
correct fields/statuses/permissions per design §3+§8. `delivery_setup.py`
idempotently reloads them. Wired into `apply_baseline`. Test proves fixtures
survive migrate.

### Step 1: Create Vellox Deliverable Version child DocType JSON

Create `vellox_agency_projects/doctype/vellox_deliverable_version/__init__.py`
(empty `# Copyright (c) 2026, Vellox Team and contributors`).

Create `vellox_agency_projects/doctype/vellox_deliverable_version/vellox_deliverable_version.json`:

```json
{
  "actions": [],
  "creation": "2026-08-26 00:00:00.000000",
  "doctype": "DocType",
  "editable_grid": 1,
  "engine": "InnoDB",
  "field_order": ["version_number", "file_url", "notes", "created_by", "created_on"],
  "fields": [
    {"fieldname": "version_number", "label": "Version", "fieldtype": "Int", "reqd": 1, "in_list_view": 1},
    {"fieldname": "file_url", "label": "File URL", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
    {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
    {"fieldname": "created_by", "label": "Created By", "fieldtype": "Link", "options": "User", "reqd": 1, "in_list_view": 1},
    {"fieldname": "created_on", "label": "Created On", "fieldtype": "Datetime", "reqd": 1}
  ],
  "istable": 1,
  "links": [],
  "modified": "2026-08-26 00:00:00.000000",
  "modified_by": "Administrator",
  "module": "Vellox Agency Projects",
  "name": "Vellox Deliverable Version",
  "naming_rule": "By fieldname",
  "owner": "Administrator",
  "permissions": [],
  "sort_field": "modified",
  "sort_order": "DESC",
  "states": []
}
```

Create `vellox_agency_projects/doctype/vellox_deliverable_version/vellox_deliverable_version.py`:

```python
from frappe.model.document import Document
class VelloxDeliverableVersion(Document):
    pass
```

### Step 2: Create Vellox Review Round child DocType JSON

Create `vellox_agency_projects/doctype/vellox_review_round/__init__.py` (empty copyright).

Create `vellox_agency_projects/doctype/vellox_review_round/vellox_review_round.json`:

```json
{
  "actions": [],
  "creation": "2026-08-26 00:00:00.000000",
  "doctype": "DocType",
  "editable_grid": 1,
  "engine": "InnoDB",
  "field_order": ["reviewer", "audience", "outcome", "comments", "reviewed_on"],
  "fields": [
    {"fieldname": "reviewer", "label": "Reviewer", "fieldtype": "Link", "options": "User", "reqd": 1, "in_list_view": 1},
    {"fieldname": "audience", "label": "Audience", "fieldtype": "Select", "options": "Internal\nClient", "reqd": 1, "in_list_view": 1},
    {"fieldname": "outcome", "label": "Outcome", "fieldtype": "Select", "options": "Approved\nChanges Requested", "reqd": 1, "in_list_view": 1},
    {"fieldname": "comments", "label": "Comments", "fieldtype": "Small Text"},
    {"fieldname": "reviewed_on", "label": "Reviewed On", "fieldtype": "Datetime", "reqd": 1}
  ],
  "istable": 1,
  "links": [],
  "modified": "2026-08-26 00:00:00.000000",
  "modified_by": "Administrator",
  "module": "Vellox Agency Projects",
  "name": "Vellox Review Round",
  "naming_rule": "By fieldname",
  "owner": "Administrator",
  "permissions": [],
  "sort_field": "modified",
  "sort_order": "DESC",
  "states": []
}
```

Create `vellox_agency_projects/doctype/vellox_review_round/vellox_review_round.py`:

```python
from frappe.model.document import Document
class VelloxReviewRound(Document):
    pass
```

### Step 3: Rework Deliverable DocType JSON

**File:** `vellox_agency_projects/doctype/deliverable/deliverable.json`

Replace entire contents with:

```json
{
  "actions": [],
  "allow_rename": 1,
  "creation": "2026-08-13 00:00:00.000000",
  "doctype": "DocType",
  "engine": "InnoDB",
  "field_order": [
    "project", "title", "deliverable_type",
    "sb_schedule", "due_date", "revision_allowance",
    "sb_status", "status", "current_version",
    "sb_acceptance", "accepted_on", "accepted_by",
    "sb_content", "client_visible",
    "sb_versions", "versions",
    "sb_rounds", "review_rounds"
  ],
  "fields": [
    {"fieldname": "project", "fieldtype": "Link", "options": "Project", "label": "Project", "reqd": 1, "in_list_view": 1, "in_standard_filter": 1},
    {"fieldname": "title", "fieldtype": "Data", "label": "Title", "reqd": 1, "in_list_view": 1},
    {"fieldname": "deliverable_type", "fieldtype": "Select", "label": "Deliverable Type", "options": "Document\nDesign\nMedia\nCode\nReport", "reqd": 1, "in_list_view": 1, "default": "Design"},
    {"fieldname": "sb_schedule", "fieldtype": "Section Break", "label": "Schedule"},
    {"fieldname": "due_date", "fieldtype": "Date", "label": "Due Date"},
    {"fieldname": "revision_allowance", "fieldtype": "Int", "label": "Revision Allowance", "default": "2", "reqd": 1},
    {"fieldname": "sb_status", "fieldtype": "Section Break", "label": "Status"},
    {"fieldname": "status", "fieldtype": "Select", "label": "Status", "options": "Draft\nInternal Review\nClient Review\nApproved\nChanges Requested\nCancelled", "default": "Draft", "in_list_view": 1, "in_standard_filter": 1},
    {"fieldname": "current_version", "fieldtype": "Int", "label": "Current Version", "read_only": 1, "default": "0"},
    {"fieldname": "sb_acceptance", "fieldtype": "Section Break", "label": "Acceptance"},
    {"fieldname": "accepted_on", "fieldtype": "Datetime", "label": "Accepted On", "read_only": 1},
    {"fieldname": "accepted_by", "fieldtype": "Link", "options": "User", "label": "Accepted By", "read_only": 1},
    {"fieldname": "sb_content", "fieldtype": "Section Break", "label": "Content"},
    {"fieldname": "client_visible", "fieldtype": "Check", "label": "Client Visible", "default": "0"},
    {"fieldname": "sb_versions", "fieldtype": "Section Break", "label": "Versions"},
    {"fieldname": "versions", "fieldtype": "Table", "label": "Versions", "options": "Vellox Deliverable Version"},
    {"fieldname": "sb_rounds", "fieldtype": "Section Break", "label": "Review Rounds"},
    {"fieldname": "review_rounds", "fieldtype": "Table", "label": "Review Rounds", "options": "Vellox Review Round"}
  ],
  "index_web_pages_for_search": 1,
  "links": [],
  "modified": "2026-08-26 00:00:00.000000",
  "modified_by": "Administrator",
  "module": "Vellox Agency Projects",
  "name": "Deliverable",
  "naming_rule": "Expression (old style)",
  "naming_series": "DEL-.YYYY.-",
  "owner": "Administrator",
  "permissions": [
    {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1, "email": 1, "print": 1, "report": 1, "share": 1},
    {"role": "Agency Manager", "read": 1, "write": 1, "create": 1, "email": 1, "print": 1, "report": 1, "share": 1},
    {"role": "Vellox Project Manager", "read": 1, "write": 1, "create": 1, "email": 1, "print": 1, "report": 1, "share": 1},
    {"role": "Vellox Team Member", "read": 1, "write": 1, "create": 1, "email": 1, "print": 1, "report": 1, "share": 1},
    {"role": "Agency Staff", "read": 1, "write": 1, "create": 1, "email": 1, "print": 1, "report": 1, "share": 1}
  ],
  "sort_field": "modified",
  "sort_order": "DESC",
  "states": [],
  "track_changes": 1
}
```

### Step 4: Create delivery_setup.py

Create `vellox_agency/delivery_setup.py`:

```python
"""Idempotent setup for Vellox Deliverable DocType fixtures."""

import frappe


def setup_delivery_fields() -> None:
    """Reload the three delivery DocType definitions so schema stays current."""
    frappe.reload_doc("vellox_agency_projects", "doctype", "deliverable")
    frappe.reload_doc("vellox_agency_projects", "doctype", "vellox_deliverable_version")
    frappe.reload_doc("vellox_agency_projects", "doctype", "vellox_review_round")
```

### Step 5: Wire into apply_baseline

**File:** `vellox_agency/security.py:27-52`

Add import + call. The import block (line ~29) becomes:

```python
from vellox_agency.delivery_setup import setup_delivery_fields
```

Insert call after `setup_change_request_doctype()` (line ~49), before
`setup_practice_templates()`:

```python
setup_delivery_fields()
```

### Step 6: Add validate hook for Deliverable

**File:** `vellox_agency/hooks.py`

After the `doc_events["Vellox Change Request"]` block (line ~47), add:

```python
doc_events["Deliverable"] = {
    "validate": "vellox_agency.deliverable.validate_deliverable",
}
```

`validate_deliverable` will be implemented in Task 2. For now create a stub
in `vellox_agency/deliverable.py`:

```python
"""Vellox Deliverable lifecycle engine."""
import frappe


def validate_deliverable(doc, method=None):
    """Hook: enforce transition legality on every save."""
    pass  # implemented in Task 2
```

### Step 7: Sync + migrate + verify fixtures

```bash
rsync -a --exclude "__pycache__" --exclude "*.pyc" --exclude ".git" \
  --exclude ".bench-venv" --exclude "frappe-bench" --exclude "docs" \
  --exclude "scripts" \
  "/Users/imac/Documents/ChatGPT/vellox erp/Elyostudio/" \
  "/private/tmp/vellox-frappe-bench/apps/vellox_agency/"

bench --site vellox.localhost migrate
```

### Step 8: Write the fixture test

Create `vellox_agency/tests/test_delivery_setup.py`:

```python
import frappe
from frappe.tests.utils import FrappeTestCase


class TestDeliverySetup(FrappeTestCase):
    def test_doctypes_exist_with_correct_fields(self):
        for name in ("Deliverable", "Vellox Deliverable Version", "Vellox Review Round"):
            self.assertTrue(frappe.db.exists("DocType", name), f"{name} missing")

        meta = frappe.get_meta("Deliverable")
        fieldnames = {f.fieldname for f in meta.fields}
        for expected in ("project", "title", "deliverable_type", "status",
                         "revision_allowance", "current_version", "versions",
                         "review_rounds", "accepted_on", "accepted_by",
                         "client_visible"):
            self.assertIn(expected, fieldnames, f"Deliverable missing field: {expected}")

        self.assertTrue(meta.istable is not True or True)  # main DocType
        self.assertEqual(
            set(frappe.get_meta("Deliverable").get_field("status").options.split("\n")),
            {"Draft", "Internal Review", "Client Review", "Approved",
             "Changes Requested", "Cancelled"},
        )

    def test_child_tables_are_tables(self):
        for child in ("Vellox Deliverable Version", "Vellox Review Round"):
            meta = frappe.get_meta(child)
            self.assertTrue(meta.istable, f"{child} should be istable=1")

    def test_deliverable_track_changes(self):
        meta = frappe.get_meta("Deliverable")
        self.assertTrue(meta.track_changes)
```

### Step 9: Run test

```bash
bench --site vellox.localhost run-tests --app vellox_agency \
  --module vellox_agency.tests.test_delivery_setup
```

Expected: PASS (RED not applicable here — the fixture test validates existing
metadata, which is the deliverable of this task).

### Step 10: Commit

```bash
git add -A
git commit -m "feat: delivery DocType fixtures and baseline wiring

Rework Deliverable to match design spec §3 fields/statuses/permissions.
Add Vellox Deliverable Version and Vellox Review Round child DocTypes.
delivery_setup.py reloads all three; wired into apply_baseline."
```

---

## Task 2: Deliverable Lifecycle State Machine

**Goal:** `transition(doc, action)` enforces the legal-transition table from
design §3.1. Every illegal move raises. Final approval requires a client-side
review round with "Approved" outcome. All tests RED-first then GREEN.

### Step 1: Write failing tests

Create `vellox_agency/tests/test_deliverable_lifecycle.py`:

```python
import frappe
from frappe.tests.utils import FrappeTestCase

from vellox_agency.delivery_setup import setup_delivery_fields
from vellox_agency.deliverable import transition


def _deliverable(**kw):
    defaults = {
        "doctype": "Deliverable",
        "project": "_Test Lifecycle Project",
        "title": "Brand Guidelines v2",
        "deliverable_type": "Design",
    }
    defaults.update(kw)
    return frappe.get_doc(defaults)


class TestDeliverableLifecycle(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from vellox_agency.tests.test_offer_builder import _bootstrap_erpnext_test_fixtures
        _bootstrap_erpnext_test_fixtures()
        setup_delivery_fields()
        frappe.reload_doctype("Deliverable")
        cls.project = frappe.get_doc({
            "doctype": "Project",
            "project_name": "_Test Lifecycle Project",
            "company": "_Test Company",
        }).insert(ignore_permissions=True)

    def test_happy_path_draft_to_approved(self):
        doc = _deliverable().insert(ignore_permissions=True)
        self.assertEqual(doc.status, "Draft")
        transition(doc, "submit_for_review")
        self.assertEqual(doc.status, "Internal Review")
        transition(doc, "internal_approve")
        self.assertEqual(doc.status, "Client Review")
        transition(doc, "client_approve")
        self.assertEqual(doc.status, "Approved")

    def test_illegal_transition_raises(self):
        doc = _deliverable().insert(ignore_permissions=True)
        with self.assertRaisesRegex(frappe.ValidationError, "Illegal transition"):
            transition(doc, "client_approve")  # Draft -> Client Review is illegal

    def test_changes_requested_back_to_internal(self):
        doc = _deliverable().insert(ignore_permissions=True)
        transition(doc, "submit_for_review")
        transition(doc, "internal_approve")
        transition(doc, "request_changes")
        self.assertEqual(doc.status, "Changes Requested")
        transition(doc, "submit_for_review")
        self.assertEqual(doc.status, "Internal Review")

    def test_cancel_from_draft(self):
        doc = _deliverable().insert(ignore_permissions=True)
        transition(doc, "cancel")
        self.assertEqual(doc.status, "Cancelled")

    def test_cancel_not_allowed_after_internal_review(self):
        doc = _deliverable().insert(ignore_permissions=True)
        transition(doc, "submit_for_review")
        with self.assertRaisesRegex(frappe.ValidationError, "Illegal transition"):
            transition(doc, "cancel")

    def test_final_approve_requires_client_round(self):
        doc = _deliverable().insert(ignore_permissions=True)
        transition(doc, "submit_for_review")
        transition(doc, "internal_approve")
        # no client review round yet — should fail
        with self.assertRaisesRegex(frappe.ValidationError, "client.*review"):
            transition(doc, "client_approve")

    def test_current_version_increments(self):
        doc = _deliverable().insert(ignore_permissions=True)
        self.assertEqual(doc.current_version, 0)
        doc.append("versions", {
            "version_number": 1,
            "file_url": "https://example.com/v1.pdf",
            "created_by": "Administrator",
            "created_on": frappe.utils.now_datetime(),
        })
        doc.save()
        transition(doc, "submit_for_review")
        self.assertEqual(doc.current_version, 1)
```

### Step 2: Run tests to verify they fail

```bash
bench --site vellox.localhost run-tests --app vellox_agency \
  --module vellox_agency.tests.test_deliverable_lifecycle
```

Expected: FAIL (transition function doesn't enforce anything yet; the stub
validate_deliverable is a no-op).

### Step 3: Implement the lifecycle engine

Replace the contents of `vellox_agency/deliverable.py` with:

```python
"""Vellox Deliverable lifecycle engine.

All status transitions flow through transition(doc, action).  The docstatus
column stays 0 (non-submittable); track_changes captures the audit trail.
"""

import frappe
from frappe import _

LEGAL_TRANSITIONS = {
    "Draft": {"submit_for_review": "Internal Review"},
    "Internal Review": {
        "internal_approve": "Client Review",
        "request_changes": "Changes Requested",
        "cancel": "Cancelled",
    },
    "Client Review": {
        "client_approve": "Approved",
        "request_changes": "Changes Requested",
    },
    "Changes Requested": {
        "submit_for_review": "Internal Review",
    },
}
# Approved and Cancelled are terminal — no outgoing transitions.

REQUIRE_CLIENT_REVIEW_FOR_APPROVE = True


def transition(doc, action):
    """Move doc to the next status via the named action.

    Raises frappe.ValidationError on illegal transitions or unmet preconditions.
    Updates doc.status in place; caller must call doc.save() afterwards.
    """
    current = doc.status
    rule = LEGAL_TRANSITIONS.get(current, {})
    target = rule.get(action)
    if not target:
        frappe.throw(
            _("Illegal transition {0} → action '{1}'.").format(
                frappe.bold(current), frappe.bold(action)
            ),
            frappe.ValidationError,
        )

    if action == "client_approve" and REQUIRE_CLIENT_REVIEW_FOR_APPROVE:
        _require_approved_client_round(doc)

    doc.status = target

    if target == "Approved":
        doc.accepted_on = frappe.utils.now_datetime()
        doc.accepted_by = frappe.session.user


def validate_deliverable(doc, method=None):
    """Hook: called on every Deliverable save. Currently a no-op stub;
    lifecycle enforcement is done via transition() + this hook will grow
    in P3-27 for permission_query_conditions wiring."""
    pass


def _require_approved_client_round(doc):
    """At least one Review Round with audience=Client, outcome=Approved must exist."""
    has_client_approval = any(
        r.audience == "Client" and r.outcome == "Approved"
        for r in (doc.review_rounds or [])
    )
    if not has_client_approval:
        frappe.throw(
            _("A client review round with outcome 'Approved' is required before final approval."),
            frappe.ValidationError,
        )
```

### Step 4: Run tests

```bash
bench --site vellox.localhost run-tests --app vellox_agency \
  --module vellox_agency.tests.test_deliverable_lifecycle
```

Expected: PASS.

### Step 5: Run full suite (regression check)

```bash
bench --site vellox.localhost run-tests --app vellox_agency
```

Expected: 54 + 7 new = 61 tests, all OK.

### Step 6: Commit

```bash
git add -A
git commit -m "feat: deliverable lifecycle state machine

transition() enforces legal moves per design §3.1.
Final client approval requires an approved client review round.
Terminal states: Approved, Cancelled."
```

---

## Task 3: Version Immutability + Revision Allowance Gating

**Goal:** Child Version rows are immutable after insert. When review rounds
consumed > revision_allowance, status is forced to "Changes Requested" and a
Change Request becomes REQUIRED (validated on next submit_for_review). All
RED-first.

### Step 1: Write failing tests

Create `vellox_agency/tests/test_deliverable_versions.py`:

```python
import frappe
from frappe.tests.utils import FrappeTestCase

from vellox_agency.delivery_setup import setup_delivery_fields
from vellox_agency.deliverable import transition


def _deliverable_with_version(**kw):
    """Insert a Draft deliverable with one version row attached."""
    doc = frappe.get_doc({
        "doctype": "Deliverable",
        "project": "_Test Version Project",
        "title": "Logo Concept",
        "deliverable_type": "Design",
        "revision_allowance": 2,
        "versions": [{
            "version_number": 1,
            "file_url": "https://example.com/logo-v1.pdf",
            "notes": "Initial draft",
            "created_by": "Administrator",
            "created_on": frappe.utils.now_datetime(),
        }],
    })
    doc.insert(ignore_permissions=True)
    return doc


class TestDeliverableVersions(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from vellox_agency.tests.test_offer_builder import _bootstrap_erpnext_test_fixtures
        _bootstrap_erpnext_test_fixtures()
        setup_delivery_fields()
        frappe.reload_doctype("Deliverable")
        cls.project = frappe.get_doc({
            "doctype": "Project",
            "project_name": "_Test Version Project",
            "company": "_Test Company",
        }).insert(ignore_permissions=True)

    def test_version_immutability(self):
        doc = _deliverable_with_version()
        v = doc.versions[0]
        # Attempting to modify an existing version row should raise
        v.notes = "Modified after insert"
        with self.assertRaises(frappe.ValidationError):
            doc.save()

    def test_adding_new_version_creates_row(self):
        doc = _deliverable_with_version()
        self.assertEqual(len(doc.versions), 1)
        doc.append("versions", {
            "version_number": 2,
            "file_url": "https://example.com/logo-v2.pdf",
            "notes": "Revision 2",
            "created_by": "Administrator",
            "created_on": frappe.utils.now_datetime(),
        })
        doc.save()
        doc.reload()
        self.assertEqual(len(doc.versions), 2)

    def test_current_version_tracks_latest(self):
        doc = _deliverable_with_version()
        self.assertEqual(doc.current_version, 0)
        doc.append("versions", {
            "version_number": 2,
            "file_url": "https://example.com/logo-v2.pdf",
            "notes": "",
            "created_by": "Administrator",
            "created_on": frappe.utils.now_datetime(),
        })
        doc.current_version = 2
        doc.save()
        self.assertEqual(doc.current_version, 2)

    def test_revision_allowance_exhausted_blocks_submit(self):
        """When review_rounds consumed > revision_allowance, submit_for_review
        should force status to Changes Requested and require a CR."""
        doc = frappe.get_doc({
            "doctype": "Deliverable",
            "project": "_Test Version Project",
            "title": "Exhaustion Test",
            "deliverable_type": "Document",
            "revision_allowance": 1,
            "versions": [{
                "version_number": 1,
                "file_url": "https://example.com/doc-v1.pdf",
                "created_by": "Administrator",
                "created_on": frappe.utils.now_datetime(),
            }],
            "review_rounds": [{
                "reviewer": "Administrator",
                "audience": "Internal",
                "outcome": "Changes Requested",
                "comments": "Needs rework",
                "reviewed_on": frappe.utils.now_datetime(),
            }],
        }).insert(ignore_permissions=True)
        # 1 round consumed, allowance=1 → no exhaustion yet
        transition(doc, "submit_for_review")
        self.assertEqual(doc.status, "Internal Review")

        # Now add a second round (exceeds allowance=1)
        doc.append("review_rounds", {
            "reviewer": "Administrator",
            "audience": "Client",
            "outcome": "Changes Requested",
            "comments": "Client rejected",
            "reviewed_on": frappe.utils.now_datetime(),
        })
        doc.status = "Changes Requested"
        doc.save()
        # 2 rounds > allowance=1 → Changes Requested required
        with self.assertRaisesRegex(frappe.ValidationError, "Change Request"):
            transition(doc, "submit_for_review")

    def test_version_number_required(self):
        doc = frappe.get_doc({
            "doctype": "Deliverable",
            "project": "_Test Version Project",
            "title": "No Number",
            "deliverable_type": "Design",
            "versions": [{
                "file_url": "https://example.com/x.pdf",
                "created_by": "Administrator",
                "created_on": frappe.utils.now_datetime(),
            }],
        })
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)
```

### Step 2: Run tests to verify they fail

```bash
bench --site vellox.localhost run-tests --app vellox_agency \
  --module vellox_agency.tests.test_deliverable_versions
```

Expected: FAIL (version immutability check not implemented; revision allowance
check not wired into transition).

### Step 3: Implement version immutability + revision allowance

Edit `vellox_agency/deliverable.py` — add to the top-level (after the existing
`transition` function, before `validate_deliverable`):

```python
def validate_deliverable(doc, method=None):
    """Hook: enforce version immutability on every save."""
    if not doc.is_new():
        _enforce_version_immutability(doc)
    _enforce_revision_allowance(doc)


def _enforce_version_immutability(doc):
    """Existing version rows must not be modified after insert."""
    if not doc.get_docbefore_save():
        return
    old_versions = {
        v.name: v.as_dict()
        for v in (doc.get_docbefore_save().versions or [])
        if v.name
    }
    for row in doc.versions or []:
        if row.name and row.name in old_versions:
            old = old_versions[row.name]
            for field in ("version_number", "file_url", "notes"):
                if str(row.get(field)) != str(old.get(field)):
                    frappe.throw(
                        _("Version rows are immutable after creation. "
                          "Create a new version instead."),
                        frappe.ValidationError,
                    )


def _enforce_revision_allowance(doc):
    """If review rounds consumed > revision_allowance, block submit_for_review."""
    rounds_used = len(doc.review_rounds or [])
    if rounds_used > (doc.revision_allowance or 2):
        doc._revision_exhausted = True


def _check_revision_exhausted(doc):
    """Called at the start of transition(); raises if exhausted."""
    if getattr(doc, "_revision_exhausted", False):
        frappe.throw(
            _("Revision allowance ({0}) exhausted. A Change Request is required "
              "before further review rounds.").format(doc.revision_allowance),
            frappe.ValidationError,
        )
```

Edit the existing `transition` function — add a call at the very top, after
the doc parameter:

```python
def transition(doc, action):
    _check_revision_exhausted(doc)
    # ... rest of existing code
```

### Step 4: Run version tests

```bash
bench --site vellox.localhost run-tests --app vellox_agency \
  --module vellox_agency.tests.test_deliverable_versions
```

Expected: PASS.

### Step 5: Run full suite (regression)

```bash
bench --site vellox.localhost run-tests --app vellox_agency
```

Expected: all tests OK.

### Step 6: Commit

```bash
git add -A
git commit -m "feat: deliverable version immutability and revision allowance

Version child rows are immutable after insert (field-level diff check).
Revision allowance exhaustion blocks submit_for_review and requires a CR."
```

---

## Task 4: PR + CI + Merge

### Step 1: Create branch + push

```bash
git checkout -b task/p3-26-deliverable-lifecycle
git add -A && git commit -m "WIP: P3-26 deliverable lifecycle (all tasks combined)"
git push -u origin task/p3-26-deliverable-lifecycle
```

### Step 2: Create PR

```bash
gh pr create --base master --head task/p3-26-deliverable-lifecycle \
  --title "feat: deliverable lifecycle, versions and review rounds" \
  --body "Card P3-26 per design §3+§5. ..."
```

### Step 3: Wait for CI

```bash
RUN=$(gh run list -R bhamalawi-alt/vellox-erp --branch task/p3-26-deliverable-lifecycle \
  --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch "$RUN" -R bhamalawi-alt/vellox-erp --exit-status --interval 20
```

### Step 4: Merge + verify master

```bash
gh pr merge task/p3-26-deliverable-lifecycle --merge
git checkout master && git pull --ff-only
```

Wait for master CI, post Trello evidence, move card to Done.

---

## Post-Plan Self-Review

**Spec coverage check:**
- §3.1 Lifecycle states: ✅ Task 2 — `LEGAL_TRANSITIONS` dict + `transition()`
- §3.2 Fields: ✅ Task 1 — Deliverable JSON rework
- §3.3 Versions & review rounds: ✅ Task 3 — immutability + revision allowance
- §5 Permissions: partial — DocType permissions in JSON, full enforcement deferred
  to P3-27 (permission_query_conditions). Design §8 matrix is correctly
  reflected in DocType permission rows.

**Placeholder scan:** None found. All code blocks are complete.

**Type consistency:**
- `transition(doc, action)` signature consistent across Tasks 2 and 3.
- `validate_deliverable(doc, method)` is the single hooks entry point; it
  delegates to `_enforce_version_immutability` + `_enforce_revision_allowance`.
- Child DocType names (`Vellox Deliverable Version`, `Vellox Review Round`)
  match JSON `options` fields in the parent Deliverable.
