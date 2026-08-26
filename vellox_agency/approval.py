"""Commercial approval thresholds on Quotation (design section 5).

Submission is gated server-side: quotations whose discount/margin band
requires review can only be submitted after an authorized user approves.
Auto-approved bands are stamped automatically.
"""

import frappe
from frappe import _
from frappe.utils import flt

APPROVAL_ROLES = ("Vellox Operations", "Agency Manager", "System Manager")


def _discount_percent(doc) -> float:
	gross = sum(flt(row.amount) for row in (doc.get("items") or []))
	if gross <= 0 or flt(doc.net_total) <= 0:
		return 0.0
	return round((gross - flt(doc.net_total)) / gross * 100, 2)


def required_approver_role(doc) -> str | None:
	"""None means auto-approved."""
	margin = flt(doc.get("custom_vellox_estimated_margin"))
	discount = _discount_percent(doc)
	if discount <= 5 and margin >= 40:
		return None
	if discount <= 15 and margin >= 25:
		return "Vellox Operations"
	return "Agency Manager"


def stamp_approval_on_validate(doc, method=None) -> None:
	if doc.doctype != "Quotation":
		return
	if required_approver_role(doc) is None and not doc.custom_vellox_approved_by:
		doc.custom_vellox_approval_status = "Approved"
		doc.custom_vellox_approved_by = "auto"


def gate_submission(doc, method=None) -> None:
	if doc.doctype != "Quotation":
		return
	if required_approver_role(doc) is None:
		return
	if doc.custom_vellox_approval_status != "Approved":
		frappe.throw(
			_("This quotation needs commercial approval ({0}) before submission.").format(
				frappe.bold(required_approver_role(doc))
			),
			frappe.ValidationError,
		)


@frappe.whitelist()
def approve_quotation(quotation: str):
	doc = frappe.get_doc("Quotation", quotation)
	doc.check_permission("submit")
	required = required_approver_role(doc)
	if required and not set(APPROVAL_ROLES) & set(frappe.get_roles()):
		frappe.throw(
			_("Only {0} can approve this quotation.").format(frappe.bold(required)),
			frappe.PermissionError,
		)
	doc.custom_vellox_approval_status = "Approved"
	doc.custom_vellox_approved_by = frappe.session.user
	doc.save(ignore_permissions=True)
	return {"ok": True}
