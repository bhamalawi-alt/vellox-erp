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


APPROVAL_FIELDS = ("custom_vellox_approval_status", "custom_vellox_approved_by", "custom_vellox_approval_terms")


def _commercial_terms(doc) -> str:
	"""What an approval covers: a change to any of these re-opens it."""
	gross = sum(flt(row.amount) for row in (doc.get("items") or []))
	return f"{flt(gross, 2)}|{flt(doc.net_total, 2)}|{flt(doc.get('custom_vellox_estimated_margin'), 2)}"


def _set_approval(doc, status: str, approved_by: str | None, terms: str | None) -> None:
	doc.custom_vellox_approval_status = status
	doc.custom_vellox_approved_by = approved_by
	doc.custom_vellox_approval_terms = terms


def stamp_approval_on_validate(doc, method=None) -> None:
	"""Keep the approval fields honest on every save.

	They change only through approve_quotation (which sets the flag) or here;
	edits from the form or API are dropped. An approval stays valid only while
	the commercial terms it was given for are unchanged.
	"""
	if doc.doctype != "Quotation":
		return
	if not doc.flags.vellox_approving:
		before = None if doc.is_new() else doc.get_doc_before_save()
		if before:
			_set_approval(doc, *(before.get(field) for field in APPROVAL_FIELDS))
		else:
			_set_approval(doc, "Pending", None, None)

	terms = _commercial_terms(doc)
	if doc.flags.vellox_approving:
		doc.custom_vellox_approval_terms = terms
	elif required_approver_role(doc) is None:
		if doc.custom_vellox_approval_status != "Approved" or doc.custom_vellox_approved_by == "auto":
			_set_approval(doc, "Approved", "auto", terms)
	elif doc.custom_vellox_approval_status == "Approved" and doc.custom_vellox_approval_terms != terms:
		_set_approval(doc, "Pending", None, None)


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


def _approval_refusal(doc) -> tuple[str, type[Exception]] | None:
	"""Why the session user may not approve this quotation now, or None if they may."""
	if doc.docstatus != 0:
		return _("Only a draft quotation can be approved."), frappe.ValidationError
	required = required_approver_role(doc)
	if not required:
		return _("This quotation is within the auto-approved band."), frappe.ValidationError
	if doc.get("custom_vellox_approval_status") == "Approved":
		return _("This quotation is already approved."), frappe.ValidationError
	if not set(APPROVERS[required]) & set(frappe.get_roles()):
		return _("Only {0} can approve this quotation.").format(frappe.bold(required)), frappe.PermissionError
	return None


def can_approve(doc) -> bool:
	"""True if the session user may approve this draft quotation now."""
	return _approval_refusal(doc) is None and bool(frappe.has_permission("Quotation", "submit"))


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
	doc = frappe.get_doc("Quotation", quotation, for_update=True)
	doc.check_permission("submit")
	if refusal := _approval_refusal(doc):
		message, exc = refusal
		frappe.throw(message, exc)
	doc.custom_vellox_approval_status = "Approved"
	doc.custom_vellox_approved_by = frappe.session.user
	doc.flags.vellox_approving = True
	doc.save(ignore_permissions=True)
	return {"ok": True}
