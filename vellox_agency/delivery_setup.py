"""Idempotent setup for Vellox Deliverable DocType fixtures."""

import frappe

# Each notification fires once, after a save that changes `status` to a matching
# value ("Value Change" event). Frappe skips unchanged saves, so re-saving never
# resends, and nothing is sent for a save that fails validation.
NOTIFICATION_DEFINITIONS = [
    {
        "name": "Vellox Deliverable Client Review",
        "subject": "Deliverable sent to client review: {{ doc.title }}",
        "document_type": "Deliverable",
        "event": "Value Change",
        "value_changed": "status",
        "condition": "doc.status == 'Client Review'",
        "channel": "Email",
        "recipients": [{"receiver_by_document_field": "owner"}],
        "message": "Deliverable '{{ doc.title }}' has been sent to client review.",
    },
    {
        "name": "Vellox Deliverable Client Decision",
        "subject": "Client decision on: {{ doc.title }}",
        "document_type": "Deliverable",
        "event": "Value Change",
        "value_changed": "status",
        "condition": "doc.status in ('Approved', 'Changes Requested')",
        "channel": "Email",
        "recipients": [{"receiver_by_document_field": "owner"}],
        "message": "A client decision has been recorded on '{{ doc.title }}'.",
    },
    {
        "name": "Vellox Change Request Decision",
        "subject": "Change Request {{ doc.name }}: {{ doc.status }}",
        "document_type": "Vellox Change Request",
        "event": "Value Change",
        "value_changed": "status",
        "condition": "doc.status in ('Approved', 'Rejected')",
        "channel": "Email",
        "recipients": [{"receiver_by_document_field": "owner"}],
        "message": "Change Request '{{ doc.title }}' has been {{ doc.status }}.",
    },
    {
        "name": "Vellox Revision Allowance Exhausted",
        "subject": "Revision allowance exhausted: {{ doc.title }}",
        "document_type": "Deliverable",
        "event": "Value Change",
        "value_changed": "status",
        "condition": "doc.status == 'Changes Requested' and doc.flags.revision_exhausted",
        "channel": "Email",
        "recipients": [{"receiver_by_role": "Agency Manager"}],
        "message": "Deliverable '{{ doc.title }}' has exhausted its revision allowance. A Change Request is required.",
    },
]


def setup_delivery_fields() -> None:
    """Reload the three delivery DocType definitions + add Comment visibility field."""
    frappe.reload_doc("vellox_agency_projects", "doctype", "deliverable")
    frappe.reload_doc("vellox_agency_projects", "doctype", "vellox_deliverable_version")
    frappe.reload_doc("vellox_agency_projects", "doctype", "vellox_review_round")
    _setup_comment_visibility()
    setup_notification_fixtures()


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


def setup_notification_fixtures() -> None:
    """Create or repair the delivery Notification records.

    Existing records are updated too: sites installed before this fix carry
    "Method" notifications whose dotted-path method never fires.
    """
    for defn in NOTIFICATION_DEFINITIONS:
        name = defn["name"]
        if frappe.db.exists("Notification", name):
            doc = frappe.get_doc("Notification", name)
            doc.update({**defn, "method": None})
            doc.save(ignore_permissions=True)
        else:
            frappe.get_doc({"doctype": "Notification", **defn}).insert(ignore_permissions=True)
