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


def project_team_emails(project: str) -> str:
	"""Emails of the project's manager and members, for the Change Request decision alert."""
	users = set(frappe.get_all("Project User", filters={"parent": project, "parenttype": "Project"}, pluck="user"))
	users.add(frappe.db.get_value("Project", project, "custom_vellox_project_manager"))
	users.discard(None)
	if not users:
		return ""
	emails = frappe.get_all("User", filters={"name": ["in", list(users)], "enabled": 1}, pluck="email")
	return "\n".join(sorted(e for e in emails if e))


def validate_change_request(doc, method=None) -> None:
	if doc.doctype != "Vellox Change Request":
		return
	# Notifications can only address fields on the record itself ([P3-99]).
	doc.team_emails = project_team_emails(doc.project)
	# A blank status is Draft, and a new request counts as moving from Draft, so
	# neither can skip the checks below ([P3-146]).
	doc.status = doc.status or "Draft"
	saved = None if doc.is_new() else frappe.db.get_value("Vellox Change Request", doc.name, ["status", "approved_by"], as_dict=True)
	old_status = (saved and saved.status) or "Draft"
	# approved_by changes only on the save that approves (set below).
	doc.approved_by = saved.approved_by if saved else None

	if old_status != doc.status:
		allowed = CR_LEGAL_TRANSITIONS.get(old_status, set())
		if doc.status not in allowed:
			frappe.throw(
				_("Illegal transition {0} → {1}.").format(frappe.bold(old_status), frappe.bold(doc.status)),
				frappe.ValidationError,
			)

		if doc.status == "Approved":
			# Delivery plan section 8: a Project Manager approves when the price is
			# unchanged; the Agency Manager approves any request.
			approvers = ["Agency Manager"] if flt_(doc.price_impact) else ["Vellox Project Manager", "Agency Manager"]
			if not ({"System Manager", *approvers} & _cr_roles()):
				frappe.throw(
					_("Only {0} can approve this change request.").format(
						_(" or ").join(frappe.bold(role) for role in approvers)
					),
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
	"""on_update: move the project end date once, on the save that approves the request.

	Keyed on the status change itself, not on approved_by, which a client can send.
	"""
	if doc.doctype != "Vellox Change Request" or doc.status != "Approved":
		return
	before = doc.get_doc_before_save()
	if not before or before.status == "Approved":
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
