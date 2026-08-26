"""Idempotent setup for Vellox Deliverable DocType fixtures."""

import frappe


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
