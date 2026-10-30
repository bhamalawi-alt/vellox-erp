"""Project health gating and Change Request lifecycle enforcement."""

import frappe
from frappe import _

from vellox_agency.crm_setup import CR_LEGAL_TRANSITIONS, HEALTH_MANAGER_ROLES


def _has_health_manager_role(user=None) -> bool:
	roles = set(frappe.get_roles(user or frappe.session.user))
	return bool(roles & set(HEALTH_MANAGER_ROLES))


def gate_health_transition(doc, method=None) -> None:
	if doc.doctype != "Project":
		return
	if doc.is_new() or doc.get("__islocal"):
		return
	old = frappe.db.get_value("Project", doc.name, "custom_vellox_health")
	new = doc.get("custom_vellox_health")
	if old and new and old != new and not _has_health_manager_role():
		frappe.throw(
			_("Only project managers may change Project Health."),
			frappe.PermissionError,
		)


def _cr_roles():
	return set(frappe.get_roles())


def validate_change_request(doc, method=None) -> None:
	if doc.doctype != "Vellox Change Request":
		return
	old_status = None
	if not doc.is_new():
		old_status = frappe.db.get_value("Vellox Change Request", doc.name, "status")

	if old_status and old_status != doc.status:
		allowed = CR_LEGAL_TRANSITIONS.get(old_status, set())
		if doc.status not in allowed:
			frappe.throw(
				_("Illegal transition {0} → {1}.").format(frappe.bold(old_status), frappe.bold(doc.status)),
				frappe.ValidationError,
			)

		if doc.status == "Approved":
			required = "Agency Manager" if flt_(doc.price_impact) else "Vellox Project Manager"
			needed = {"System Manager", required}
			if not (needed & _cr_roles()):
				frappe.throw(
					_("Only {0} can approve this change request.").format(frappe.bold(required)),
					frappe.PermissionError,
				)
			doc.approved_by = frappe.session.user

		if doc.status == "Implemented":
			if flt_(doc.price_impact) and (
				not doc.amendment_quotation
				or frappe.db.get_value("Quotation", doc.amendment_quotation, "docstatus") != 1
			):
				frappe.throw(
					_("A price-impacting change request needs a SUBMITTED amendment quotation."),
					frappe.ValidationError,
				)


def shift_schedule_on_approval(doc, method=None) -> None:
	if doc.doctype != "Vellox Change Request" or doc.status != "Approved":
		return
	if doc.approved_by:  # already stamped earlier — apply once
		return
	days = int(doc.schedule_impact_days or 0)
	if days:
		end = frappe.db.get_value("Project", doc.project, "expected_end_date")
		if end:
			from frappe.utils import add_days

			frappe.db.set_value("Project", doc.project, "expected_end_date", add_days(end, days))


def flt_(v):
	try:
		return float(v or 0)
	except (TypeError, ValueError):
		return 0.0
