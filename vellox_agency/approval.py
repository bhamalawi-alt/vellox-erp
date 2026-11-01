"""Commercial approval thresholds on Quotation (design section 5).

Submission is gated server-side: quotations whose discount/margin band
requires review can only be submitted after an authorized user approves.
Auto-approved bands are stamped automatically.
"""

import hashlib
import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime

# Who may approve each tier (lead-to-project design, section 5): Operations
# approves only its own band; anything beyond it needs the Agency Manager.
APPROVERS = {
	"Vellox Operations": ("Vellox Operations", "Agency Manager", "System Manager"),
	"Agency Manager": ("Agency Manager", "System Manager"),
}


def _discount_percent(doc) -> float:
	"""Total discount against list price: item discounts, the header discount,
	and any tax row that lowers the total."""
	gross = sum(
		max(flt(row.get("price_list_rate")) * flt(row.get("qty")), flt(row.amount)) for row in (doc.get("items") or [])
	)
	revenue = flt(doc.net_total)
	for tax in doc.get("taxes") or []:
		effect = -flt(tax.tax_amount) if tax.get("add_deduct_tax") == "Deduct" else flt(tax.tax_amount)
		revenue += min(effect, 0)
	if gross <= 0 or flt(doc.net_total) <= 0:
		return 0.0
	return round((gross - revenue) / gross * 100, 2)


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
	"""Fingerprint of what an approval covers: a change to any of these re-opens it."""
	terms = {
		"party": [doc.get("quotation_to"), doc.get("party_name")],
		"currency": [doc.get("currency"), flt(doc.get("conversion_rate"), 9)],
		"items": [
			[row.item_code, flt(row.qty, 6), flt(row.rate, 6), flt(row.get("price_list_rate"), 6)]
			for row in (doc.get("items") or [])
		],
		"totals": [flt(doc.net_total, 2), flt(doc.get("grand_total"), 2)],
		"margin": flt(doc.get("custom_vellox_estimated_margin"), 2),
		"discount": _discount_percent(doc),
	}
	return hashlib.sha256(json.dumps(terms, sort_keys=True, default=str).encode()).hexdigest()


def _set_approval(doc, status: str, approved_by: str | None, terms: str | None) -> None:
	doc.custom_vellox_approval_status = status
	doc.custom_vellox_approved_by = approved_by
	doc.custom_vellox_approval_terms = terms


def _stamp_terms_setter(doc, terms: str) -> None:
	"""Remember everyone who changed the commercial terms; a value sent by a client is dropped."""
	before = None if doc.is_new() else doc.get_doc_before_save()
	setters = _terms_setters(before) if before else []
	if before is None or _commercial_terms(before) != terms:
		setters = [*setters, frappe.session.user] if frappe.session.user not in setters else setters
	doc.custom_vellox_terms_set_by = "\n".join(setters)


def _terms_setters(doc) -> list[str]:
	return [user for user in (doc.get("custom_vellox_terms_set_by") or "").splitlines() if user]


def _is_maker(doc) -> bool:
	"""The quote's creator, or anyone who changed its terms (owner, 2026-11-01, [P3-144]).

	Everyone is kept, not only the last, so a second person's small change does
	not let the first approve their own discount.
	"""
	user = frappe.session.user
	return user == doc.get("owner") or user in _terms_setters(doc)


def _maker_message(required: str) -> str:
	others = [role for role in APPROVERS[required] if role != "System Manager"]
	return _("You made this quotation or set its terms, so another {0} must approve it.").format(
		_(" or ").join(frappe.bold(role) for role in others)
	)


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
	_stamp_terms_setter(doc, terms)
	if doc.flags.vellox_approving:
		# Totals are recalculated on save; the approver must cover the tier they produce.
		required = required_approver_role(doc)
		if required and not _is_approver(required):
			frappe.throw(_("Only {0} can approve this quotation.").format(frappe.bold(required)), frappe.PermissionError)
		if required and _is_maker(doc):
			frappe.throw(_maker_message(required), frappe.PermissionError, title=_("Cannot approve own quotation"))
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


def _is_approver(required: str) -> bool:
	return bool(set(APPROVERS[required]) & set(frappe.get_roles()))


def _approval_refusal(doc) -> tuple[str, type[Exception]] | None:
	"""Why the session user may not approve this quotation now, or None if they may."""
	if doc.docstatus != 0:
		return _("Only a draft quotation can be approved."), frappe.ValidationError
	required = required_approver_role(doc)
	if not required:
		return _("This quotation is within the auto-approved band."), frappe.ValidationError
	if doc.get("custom_vellox_approval_status") == "Approved":
		return _("This quotation is already approved."), frappe.ValidationError
	if not _is_approver(required):
		return _("Only {0} can approve this quotation.").format(frappe.bold(required)), frappe.PermissionError
	if _is_maker(doc):
		return _maker_message(required), frappe.PermissionError
	return None


def _is_version_seen(doc, seen) -> bool:
	if not isinstance(seen, str) or not seen:
		return False
	try:
		return get_datetime(seen) == get_datetime(doc.modified)
	except (ValueError, TypeError):
		return False


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
def approve_quotation(quotation: str, seen: str | None = None):
	"""Approve the quotation as the approver last saw it.

	`seen` is the `modified` time of the version on the approver's screen; a
	quote changed since then is refused, so nobody approves terms they have not
	read ([P3-144]).
	"""
	doc = frappe.get_doc("Quotation", quotation, for_update=True)
	doc.check_permission("submit")
	if refusal := _approval_refusal(doc):
		message, exc = refusal
		frappe.throw(message, exc)
	if not _is_version_seen(doc, seen):
		frappe.throw(
			_("{0} changed this quotation {1}, after you opened it. Reload it and review the changes before approving.").format(
				frappe.bold(frappe.utils.get_fullname(doc.modified_by)), frappe.utils.pretty_date(doc.modified)
			),
			frappe.ValidationError,
			title=_("Quotation changed"),
		)
	doc.custom_vellox_approval_status = "Approved"
	doc.custom_vellox_approved_by = frappe.session.user
	doc.flags.vellox_approving = True
	doc.save(ignore_permissions=True)
	return {"ok": True}
