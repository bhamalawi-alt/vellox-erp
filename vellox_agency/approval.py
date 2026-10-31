"""Commercial approval thresholds on Quotation (design section 5).

Submission is gated server-side: quotations whose discount/margin band
requires review can only be submitted after an authorized user approves.
Auto-approved bands are stamped automatically.
"""

import frappe
from frappe import _
from frappe.utils import flt

# Who may approve each tier (lead-to-project design, section 5): Operations
# approves only its own band; anything beyond it needs the Agency Manager.
APPROVERS = {
	"Vellox Operations": ("Vellox Operations", "Agency Manager", "System Manager"),
	"Agency Manager": ("Agency Manager", "System Manager"),
}


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


def can_approve(doc) -> bool:
	"""True if the session user may approve this draft quotation now."""
	required = required_approver_role(doc)
	if not required or doc.docstatus != 0 or doc.get("custom_vellox_approval_status") == "Approved":
		return False
	return bool(set(APPROVERS[required]) & set(frappe.get_roles()))


def quotation_actions(doc) -> dict:
	"""Which Vellox actions the session user may take on this quotation ([P3-98]).

	The Quotation form shows buttons from this; the whitelisted methods still
	check everything again when a button is used.
	"""
	from vellox_agency.acceptance import CREATION_ROLES

	project = doc.get("custom_vellox_project")
	if project and not frappe.db.exists("Project", project):
		project = None
	can_create_project = bool(
		doc.docstatus == 1
		and not project
		and set(CREATION_ROLES) & set(frappe.get_roles())
		and frappe.has_permission("Project", "create")
	)
	visible_project = project if project and frappe.has_permission("Project", "read", doc=project) else None
	return {"can_approve": can_approve(doc), "can_create_project": can_create_project, "project": visible_project}


def add_quotation_actions(doc, method=None) -> None:
	"""Quotation onload hook: hand the form its allowed actions."""
	doc.set_onload("vellox_actions", quotation_actions(doc))


@frappe.whitelist(methods=["POST"])
def approve_quotation(quotation: str):
	doc = frappe.get_doc("Quotation", quotation)
	doc.check_permission("submit")
	if doc.docstatus != 0:
		frappe.throw(_("Only a draft quotation can be approved."), frappe.ValidationError)
	required = required_approver_role(doc)
	if required and not set(APPROVERS[required]) & set(frappe.get_roles()):
		frappe.throw(
			_("Only {0} can approve this quotation.").format(frappe.bold(required)),
			frappe.PermissionError,
		)
	doc.custom_vellox_approval_status = "Approved"
	doc.custom_vellox_approved_by = frappe.session.user
	doc.save(ignore_permissions=True)
	return {"ok": True}
