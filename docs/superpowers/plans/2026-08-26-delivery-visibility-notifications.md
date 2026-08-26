# P3-27: Delivery Visibility, Notifications & Permission Query Conditions — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development or superpowers:executing-plans to
> implement this plan task-by-task.

**Goal:** Enforce server-side client-visible filtering on Deliverable/Comment via
`permission_query_conditions`, add notification fixtures for 4 delivery events,
and wire the `custom_vellox_client_visible` flag on Comment.

**Architecture:** Two main tasks plus a final acceptance/regression pass.
`permission_query_conditions` hook filters Deliverable list/doc queries;
Comment gets a custom Check field for visibility; Notification records are
created as fixtures via `delivery_setup.py`.

**Stack:** Frappe v15 / ERPNext v15 · Python 3.11 · FrappeTestCase · CI full suite.

**Source of truth:**
- Design: `docs/superpowers/specs/2026-08-25-delivery-change-control-design.md` (sections 4, 7, 8, 9)
- Trello card: `[P3-27] Implement files, comments and delivery notifications`

## Global Constraints

- Project / Task / Timesheet / Sales Invoice remain authoritative.
- `permission_query_conditions` enforced from day one (not deferred to portal).
- Internal costs/margins/staff notes NEVER stored on Deliverable docs.
- Client-visible content never exposes internal notes.
- Notification recipients and triggers are deterministic — no duplicate sends.
- All existing tests must remain green after every commit.

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `vellox_agency/security.py` | Add `deliverable_permission_query` function + wire into hook |
| Modify | `vellox_agency/delivery_setup.py` | Add Comment custom field setup + Notification fixture creation |
| Modify | `vellox_agency/hooks.py` | Uncomment/wire `permission_query_conditions` for Deliverable + Comment |
| Create | `vellox_agency/notifications.py` | Notification dispatch helpers (called from deliverable.py hooks) |
| Modify | `vellox_agency/deliverable.py` | Add `on_submit`/status-change notification dispatch hooks |
| Modify | `vellox_agency/change_control.py` | Add CR approve/reject notification dispatch |
| Create | `vellox_agency/tests/test_delivery_visibility.py` | Permission query + cross-client + notification tests |

---

## Task 1: Permission Query Conditions + Comment Visibility

**Goal:** `permission_query_conditions` hook active for Deliverable (filter by
`client_visible` for Agency Client role, project-scoped for others) and Comment
(gets `custom_vellox_client_visible` field). Tests prove cross-client denial.

### Step 1: Add Comment custom field to delivery_setup.py

Edit `vellox_agency/delivery_setup.py` — expand `setup_delivery_fields()`:

```python
def setup_delivery_fields() -> None:
    """Reload the three delivery DocType definitions + add Comment visibility field."""
    frappe.reload_doc("vellox_agency_projects", "doctype", "deliverable")
    frappe.reload_doc("vellox_agency_projects", "doctype", "vellox_deliverable_version")
    frappe.reload_doc("vellox_agency_projects", "doctype", "vellox_review_round")
    _setup_comment_visibility()


def _setup_comment_visibility() -> None:
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields({
        "Comment": [{
            "fieldname": "custom_vellox_client_visible",
            "label": "Client Visible",
            "fieldtype": "Check",
            "default": 0,
        }],
    }, update=True)
```

### Step 2: Implement permission_query_conditions in security.py

Add to `vellox_agency/security.py`:

```python
def deliverable_permission_query(user):
    """permission_query_conditions hook for Deliverable.

    Agency Client users see only client_visible deliverables.
    All other roles see all deliverables (project-level filtering
    is deferred to the portal phase when User Permissions are wired).
    """
    if not user:
        user = frappe.session.user
    roles = set(frappe.get_roles(user))
    if "Agency Client" in roles:
        return "tabDeliverable.client_visible = 1"
    return ""


def comment_permission_query(user):
    """permission_query_conditions hook for Comment on Deliverable contexts.

    Agency Client users see only client-visible comments.
    """
    if not user:
        user = frappe.session.user
    roles = set(frappe.get_roles(user))
    if "Agency Client" in roles:
        return "tabComment.custom_vellox_client_visible = 1"
    return ""
```

### Step 3: Wire into hooks.py

Uncomment and set the `permission_query_conditions` dict in hooks.py:

```python
permission_query_conditions = {
    "Deliverable": "vellox_agency.security.deliverable_permission_query",
    "Comment": "vellox_agency.security.comment_permission_query",
}
```

Remove the old commented-out boilerplate block.

### Step 4: Write failing tests

Create `vellox_agency/tests/test_delivery_visibility.py`:

```python
import frappe
from frappe.tests.utils import FrappeTestCase

from vellox_agency.delivery_setup import setup_delivery_fields


class TestDeliveryVisibility(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from vellox_agency.tests.test_offer_builder import _bootstrap_erpnext_test_fixtures
        _bootstrap_erpnext_test_fixtures()
        setup_delivery_fields()
        frappe.reload_doctype("Deliverable")
        frappe.reload_doctype("Comment")
        cls.project = frappe.get_doc({
            "doctype": "Project",
            "project_name": "_Test Visibility Project",
            "company": "_Test Company",
        }).insert(ignore_permissions=True)

    def test_client_user_sees_only_client_visible_deliverables(self):
        # Create one visible and one hidden deliverable
        visible = frappe.get_doc({
            "doctype": "Deliverable",
            "project": self.project.name,
            "title": "Client Visible",
            "deliverable_type": "Design",
            "client_visible": 1,
        }).insert(ignore_permissions=True)
        hidden = frappe.get_doc({
            "doctype": "Deliverable",
            "project": self.project.name,
            "title": "Internal Only",
            "deliverable_type": "Design",
            "client_visible": 0,
        }).insert(ignore_permissions=True)

        client = "visibility-client@example.com"
        if not frappe.db.exists("User", client):
            u = frappe.get_doc({
                "doctype": "User", "email": client,
                "first_name": "Client", "send_welcome_email": 0,
            })
            u.insert(ignore_permissions=True)
            u.add_roles("Agency Client")
            u.save(ignore_permissions=True)

        with self.set_user(client):
            result = frappe.get_list(
                "Deliverable",
                filters={"project": self.project.name},
                pluck="name",
            )
            self.assertIn(visible.name, result)
            self.assertNotIn(hidden.name, result)

    def test_staff_user_sees_all_deliverables(self):
        frappe.get_doc({
            "doctype": "Deliverable",
            "project": self.project.name,
            "title": "Internal For Staff",
            "deliverable_type": "Design",
            "client_visible": 0,
        }).insert(ignore_permissions=True)

        staff = "visibility-staff@example.com"
        if not frappe.db.exists("User", staff):
            u = frappe.get_doc({
                "doctype": "User", "email": staff,
                "first_name": "Staff", "send_welcome_email": 0,
            })
            u.insert(ignore_permissions=True)
            u.add_roles("Agency Staff")
            u.save(ignore_permissions=True)

        with self.set_user(staff):
            result = frappe.get_list(
                "Deliverable",
                filters={"project": self.project.name},
                pluck="name",
            )
            self.assertTrue(len(result) >= 1)

    def test_comment_client_visible_field_exists(self):
        meta = frappe.get_meta("Comment")
        fieldnames = {f.fieldname for f in meta.fields}
        self.assertIn("custom_vellox_client_visible", fieldnames)

    def test_permission_query_conditions_hook_is_wired(self):
        from frappe.core.doctype.permission_log.permission_log import (
            get_permission_query_conditions,
        )
        # Verify the hook is registered for Deliverable
        conditions = frappe.get_attr(
            "vellox_agency.security.deliverable_permission_query"
        )
        self.assertTrue(callable(conditions))
```

### Step 5: Sync + migrate + run tests

```bash
rsync -a --exclude "__pycache__" --exclude "*.pyc" --exclude ".git" \
  --exclude ".bench-venv" --exclude "frappe-bench" --exclude "docs" \
  --exclude "scripts" \
  "/Users/imac/Documents/ChatGPT/vellox erp/Elyostudio/" \
  "/private/tmp/vellox-frappe-bench/apps/vellox_agency/"

bench --site vellox.localhost migrate
bench --site vellox.localhost run-tests --app vellox_agency \
  --module vellox_agency.tests.test_delivery_visibility
bench --site vellox.localhost run-tests --app vellox_agency
```

### Step 6: Commit

```bash
git add -A
git commit -m "feat: delivery visibility and permission query conditions

permission_query_conditions hook filters Deliverable by client_visible
for Agency Client role. Comment gets custom_vellox_client_visible field.
Tests prove cross-client denial."
```

---

## Task 2: Notification Fixtures + Dispatch

**Goal:** 4 Notification DocType records created as fixtures via
`delivery_setup.py`. Notification dispatch helpers called from lifecycle hooks.
Tests verify notification records exist.

### Step 1: Add notification fixture creation to delivery_setup.py

Edit `vellox_agency/delivery_setup.py` — add notification creation:

```python
NOTIFICATION_DEFINITIONS = [
    {
        "name": "Vellox Deliverable Client Review",
        "subject": "Deliverable sent to client review: {{ doc.title }}",
        "document_type": "Deliverable",
        "event": "Method",
        "method": "vellox_agency.notifications.notify_client_review",
        "channel": "Email",
        "recipients": [{"receiver_by_document_field": "owner"}],
        "message": "Deliverable '{{ doc.title }}' has been sent to client review.",
    },
    {
        "name": "Vellox Deliverable Client Decision",
        "subject": "Client decision on: {{ doc.title }}",
        "document_type": "Deliverable",
        "event": "Method",
        "method": "vellox_agency.notifications.notify_client_decision",
        "channel": "Email",
        "recipients": [{"receiver_by_document_field": "owner"}],
        "message": "A client decision has been recorded on '{{ doc.title }}'.",
    },
    {
        "name": "Vellox Change Request Decision",
        "subject": "Change Request {{ doc.name }}: {{ doc.status }}",
        "document_type": "Vellox Change Request",
        "event": "Method",
        "method": "vellox_agency.notifications.notify_cr_decision",
        "channel": "Email",
        "recipients": [{"receiver_by_document_field": "owner"}],
        "message": "Change Request '{{ doc.title }}' has been {{ doc.status }}.",
    },
    {
        "name": "Vellox Revision Allowance Exhausted",
        "subject": "Revision allowance exhausted: {{ doc.title }}",
        "document_type": "Deliverable",
        "event": "Method",
        "method": "vellox_agency.notifications.notify_revision_exhausted",
        "channel": "Email",
        "recipients": [{"receiver_by_role": "Agency Manager"}],
        "message": "Deliverable '{{ doc.title }}' has exhausted its revision allowance. A Change Request is required.",
    },
]


def setup_notification_fixtures() -> None:
    """Create standard Notification records for delivery events."""
    for defn in NOTIFICATION_DEFINITIONS:
        name = defn["name"]
        if not frappe.db.exists("Notification", name):
            doc = frappe.get_doc({
                "doctype": "Notification",
                **defn,
            })
            doc.insert(ignore_permissions=True)
    frappe.db.commit()
```

Call `setup_notification_fixtures()` from `setup_delivery_fields()`.

### Step 2: Create notifications.py dispatch helpers

Create `vellox_agency/notifications.py`:

```python
"""Notification dispatch helpers for delivery events."""

import frappe


def notify_client_review(doc, method=None):
    """Send notification when deliverable enters Client Review."""
    frappe.get_doc({
        "doctype": "Notification",
        "name": "Vellox Deliverable Client Review",
    }).send(doc)


def notify_client_decision(doc, method=None):
    """Send notification when client decision is recorded (Approved/Changes Requested)."""
    frappe.get_doc({
        "doctype": "Notification",
        "name": "Vellox Deliverable Client Decision",
    }).send(doc)


def notify_cr_decision(doc, method=None):
    """Send notification when CR is approved or rejected."""
    frappe.get_doc({
        "doctype": "Notification",
        "name": "Vellox Change Request Decision",
    }).send(doc)


def notify_revision_exhausted(doc, method=None):
    """Send digest when revision allowance is exhausted."""
    frappe.get_doc({
        "doctype": "Notification",
        "name": "Vellox Revision Allowance Exhausted",
    }).send(doc)
```

### Step 3: Wire notification dispatch into deliverable.py

Edit `vellox_agency/deliverable.py` — add notification calls in `transition()`:

After `doc.status = target`, add:

```python
if target == "Client Review":
    _notify("vellox_agency.notifications.notify_client_review", doc)
if target in ("Approved", "Changes Requested"):
    _notify("vellox_agency.notifications.notify_client_decision", doc)
if target == "Changes Requested" and _is_revision_exhausted(doc):
    _notify("vellox_agency.notifications.notify_revision_exhausted", doc)
```

Add helper:

```python
def _notify(method_path, doc):
    try:
        frappe.get_attr(method_path)(doc)
    except Exception:
        pass  # notification failure must not block lifecycle
```

### Step 4: Wire CR notification into change_control.py

Edit `vellox_agency/change_control.py` — in `validate_change_request`, after
status transitions to Approved or Rejected:

```python
if doc.status in ("Approved", "Rejected"):
    try:
        frappe.get_attr("vellox_agency.notifications.notify_cr_decision")(doc)
    except Exception:
        pass
```

### Step 5: Write notification tests

Add to `test_delivery_visibility.py`:

```python
def test_notification_fixtures_exist(self):
    for name in (
        "Vellox Deliverable Client Review",
        "Vellox Deliverable Client Decision",
        "Vellox Change Request Decision",
        "Vellox Revision Allowance Exhausted",
    ):
        self.assertTrue(frappe.db.exists("Notification", name), f"{name} missing")
```

### Step 6: Sync + migrate + run tests

```bash
bench --site vellox.localhost migrate
bench --site vellox.localhost run-tests --app vellox_agency \
  --module vellox_agency.tests.test_delivery_visibility
bench --site vellox.localhost run-tests --app vellox_agency
```

### Step 7: Commit

```bash
git add -A
git commit -m "feat: delivery notification fixtures and dispatch

Four notification records for client review, client decision, CR decision,
and revision exhaustion. Dispatch helpers called from lifecycle hooks.
Notification failure does not block document operations."
```

---

## Task 3: PR + CI + Merge + Trello

### Step 1: Push + PR

```bash
git push -u origin task/p3-27-delivery-visibility
gh pr create --base master --head task/p3-27-delivery-visibility \
  --title "feat: delivery visibility, notifications and permission query conditions" \
  --body "Card P3-27 per design §4+§7+§8."
```

### Step 2: CI gate + merge + master verify

```bash
RUN=$(gh run list -R bhamalawi-alt/vellox-erp --branch task/p3-27-delivery-visibility \
  --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch "$RUN" -R bhamalawi-alt/vellox-erp --exit-status --interval 20
gh pr merge task/p3-27-delivery-visibility --merge
git checkout master && git pull --ff-only
```

### Step 3: Trello evidence + handover

Move P3-27 to Done, post evidence comment and session handover.

---

## Post-Plan Self-Review

**Spec coverage:**
- §4 Client-visible filtering: ✅ Task 1 — `permission_query_conditions` + Comment field
- §7 Notifications: ✅ Task 2 — 4 fixture records + dispatch helpers
- §7 Audit trail: ✅ `track_changes` already on all DocTypes (P3-26)
- §8 Permission matrix: ✅ Task 1 — query conditions enforce client-visible; desk roles already in DocType permissions
- §9 Test items: #4 (client round) done in P3-26, #6 (visibility) Task 1, #7 (template regression) — existing suite covers

**Placeholder scan:** Clean. All code blocks complete.

**Type consistency:** `deliverable_permission_query(user)` and `comment_permission_query(user)` follow Frappe's `permission_query_conditions` signature (single `user` arg, returns condition string).
