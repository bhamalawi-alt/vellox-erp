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
        "recipients": [{"receiver_by_document_field": "project_manager"}],
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
        "recipients": [{"receiver_by_document_field": "team_emails"}, {"receiver_by_document_field": "owner"}],
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
    {
        "name": "Vellox Project Created",
        "subject": "Project created: {{ doc.project_name }}",
        "document_type": "Project",
        "event": "New",
        "channel": "Email",
        "recipients": [{"receiver_by_document_field": "custom_vellox_project_manager"}],
        "message": "You are the project manager of '{{ doc.project_name }}'.",
    },
]

# Recipients changed by [P3-99]: (old recipients, new recipients), used by the
# route_delivery_alerts_to_team patch on sites created before it.
REROUTED_NOTIFICATIONS = {
    "Vellox Deliverable Client Review": ([{"receiver_by_document_field": "owner"}], NOTIFICATION_DEFINITIONS[0]["recipients"]),
    "Vellox Change Request Decision": ([{"receiver_by_document_field": "owner"}], NOTIFICATION_DEFINITIONS[2]["recipients"]),
}


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


def setup_notification_fixtures(definitions: list[dict] | None = None) -> None:
    """Create missing delivery Notification records and repair broken old ones.

    Sites installed before the fix carry "Method" notifications whose
    dotted-path method never fires; only those are rewritten. Any other
    existing record is left alone so admin edits survive bench migrate.
    """
    for defn in NOTIFICATION_DEFINITIONS if definitions is None else definitions:
        name = defn["name"]
        if not frappe.db.exists("Notification", name):
            frappe.get_doc({"doctype": "Notification", **defn}).insert(ignore_permissions=True)
        elif frappe.db.get_value("Notification", name, "event") == "Method":
            doc = frappe.get_doc("Notification", name)
            doc.update({**defn, "method": None})
            doc.save(ignore_permissions=True)
