"""Vellox Deliverable lifecycle engine.

transition(doc, action) moves a deliverable by named action; validate enforces
the same status order on every save, so the form and the API follow it too
([P3-146]). The docstatus column stays 0 (non-submittable); track_changes
captures the audit trail.
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
ALLOWED_MOVES = {status: set(actions.values()) for status, actions in LEGAL_TRANSITIONS.items()}

REQUIRE_CLIENT_REVIEW_FOR_APPROVE = True


def transition(doc, action):
    """Move doc to the next status via the named action.

    Raises frappe.ValidationError on illegal transitions or unmet preconditions.
    Updates doc.status in place; caller must call doc.save() afterwards.
    """
    if _is_revision_exhausted(doc) and action == "submit_for_review":
        doc.status = "Changes Requested"
        frappe.throw(
            _("Revision allowance ({0}) exhausted. A Change Request is required "
              "before further review rounds.").format(doc.revision_allowance),
            frappe.ValidationError,
        )
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

    # Emails are sent by the Notification records in delivery_setup when the
    # caller saves the new status.
    doc.status = target

    if target == "Approved":
        doc.accepted_on = frappe.utils.now_datetime()
        doc.accepted_by = frappe.session.user

    _sync_current_version(doc)


def validate_deliverable(doc, method=None):
    """Hook: enforce the status order and version immutability on every save."""
    if not doc.is_new():
        _enforce_version_immutability(doc)
    _enforce_status_move(doc)
    # Notification conditions cannot count child rows, so the exhausted check
    # reaches the "Revision Allowance Exhausted" condition as a per-save flag.
    # Set here, not in transition(), because users also change status on the form.
    doc.flags.revision_exhausted = doc.status == "Changes Requested" and _is_revision_exhausted(doc)
    # Notifications can only address fields on the record itself ([P3-99]).
    # Falls back to the creator, who received this alert before [P3-99].
    doc.project_manager = frappe.db.get_value("Project", doc.project, "custom_vellox_project_manager") or doc.owner


def _enforce_status_move(doc):
    """Allow only the moves transition() allows, whoever saves the deliverable."""
    before = None if doc.is_new() else doc.get_doc_before_save()
    new = doc.status or "Draft"
    if not before:
        if new != "Draft":
            frappe.throw(_("A new deliverable starts as a Draft."), frappe.ValidationError)
        return
    old = before.status or "Draft"
    if old == new:
        return
    if new not in ALLOWED_MOVES.get(old, set()):
        frappe.throw(
            _("A deliverable cannot move from {0} to {1}.").format(frappe.bold(old), frappe.bold(new)),
            frappe.ValidationError,
        )
    if old == "Changes Requested" and new == "Internal Review" and _is_revision_exhausted(doc):
        frappe.throw(
            _("Revision allowance ({0}) exhausted. A Change Request is required, then a manager "
              "can raise the allowance for further review rounds.").format(doc.revision_allowance),
            frappe.ValidationError,
        )
    if new == "Approved":
        _require_approved_client_round(doc)
        doc.accepted_on = doc.accepted_on or frappe.utils.now_datetime()
        doc.accepted_by = doc.accepted_by or frappe.session.user
    _sync_current_version(doc)


def _enforce_version_immutability(doc):
    """Existing version rows must not be modified after insert."""
    if not doc.get_doc_before_save():
        return
    old_versions = {
        v.name: v.as_dict()
        for v in (doc.get_doc_before_save().versions or [])
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


def _is_revision_exhausted(doc):
    """Return True if review rounds consumed > revision_allowance."""
    rounds_used = len(doc.review_rounds or [])
    allowance = doc.revision_allowance or 0
    return rounds_used > allowance


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
