"""Qualification gate: an Opportunity may only reference a qualified Lead."""

import frappe
from frappe import _


def require_qualified_lead(doc, method=None) -> None:
	if doc.doctype != "Opportunity" or doc.opportunity_from != "Lead":
		return
	if not doc.party_name:
		return
	if frappe.db.get_value("Lead", doc.party_name, "custom_vellox_qualified"):
		return
	frappe.throw(
		_("The source Lead {0} is not qualified yet. Mark it qualified before creating an Opportunity.").format(
			frappe.bold(doc.party_name)
		),
		frappe.ValidationError,
	)
