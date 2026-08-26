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
