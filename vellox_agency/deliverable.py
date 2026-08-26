"""Vellox Deliverable lifecycle engine.

All status transitions flow through transition(doc, action).  The docstatus
column stays 0 (non-submittable); track_changes captures the audit trail.
"""

import frappe
from frappe import _

LEGAL_TRANSITIONS = {
    "Draft": {
        "submit_for_review": "Internal Review",
        "cancel": "Cancelled",
    },
    "Internal Review": {
        "internal_approve": "Client Review",
        "request_changes": "Changes Requested",
        "cancel": "Cancelled",
    },
    "Client Review": {
        "client_approve": "Approved",
        "request_changes": "Changes Requested",
        "cancel": "Cancelled",
    },
    "Changes Requested": {
        "submit_for_review": "Internal Review",
        "cancel": "Cancelled",
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

    _sync_current_version(doc)


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


def _sync_current_version(doc):
    """Set current_version to the highest version_number in the versions table."""
    versions = doc.get("versions") or []
    if versions:
        max_version = max(v.version_number for v in versions)
        doc.current_version = max_version
