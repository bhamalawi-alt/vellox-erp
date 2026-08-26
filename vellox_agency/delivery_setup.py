"""Idempotent setup for Vellox Deliverable DocType fixtures."""

import frappe


def setup_delivery_fields() -> None:
    """Reload the three delivery DocType definitions so schema stays current."""
    frappe.reload_doc("vellox_agency_projects", "doctype", "deliverable")
    frappe.reload_doc("vellox_agency_projects", "doctype", "vellox_deliverable_version")
    frappe.reload_doc("vellox_agency_projects", "doctype", "vellox_review_round")
