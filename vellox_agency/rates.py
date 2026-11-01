"""Rates and timesheet money follow job access ([P4-31], plan section 7).

Jobs without access to Activity Cost (Project Managers, Operations, team
members) see hours but no rates or amounts:
- ERPNext's whitelisted rate lookup returns zero rates to them;
- its timesheet helpers that return billing amounts, and turning timesheets
  into a sales invoice, are refused;
- on their saves a timesheet's rates are always looked up again from
  Activity Cost, so a typed-in or stale rate (Frappe keeps child-row values
  on new documents and restores hidden ones on existing rows) never stands.
"""

import frappe
from erpnext.projects.doctype.timesheet import timesheet
from frappe import _

from vellox_agency import security


def sees_rates(user: str | None = None) -> bool:
	return security.access_level("Activity Cost", user or frappe.session.user) in (None, security.VIEW, security.EDIT)


def _require_rates() -> None:
	if not sees_rates():
		frappe.throw(_("Only Finance and the Agency Manager can see timesheet rates and amounts."), frappe.PermissionError)


def _original(fn, **kwargs):
	# frappe.call drops request keys (cmd, ...) the original does not accept.
	return frappe.call(fn, **kwargs)


@frappe.whitelist()
def get_activity_cost(employee=None, activity_type=None, currency=None):
	rate = timesheet.get_activity_cost(employee=employee, activity_type=activity_type, currency=currency) or {}
	if sees_rates():
		return rate
	return {**rate, "costing_rate": 0, "billing_rate": 0}


@frappe.whitelist()
def get_projectwise_timesheet_data(**kwargs):
	_require_rates()
	return _original(timesheet.get_projectwise_timesheet_data, **kwargs)


@frappe.whitelist()
def get_timesheet_data(**kwargs):
	_require_rates()
	return _original(timesheet.get_timesheet_data, **kwargs)


@frappe.whitelist()
def get_timesheet_detail_rate(**kwargs):
	_require_rates()
	return _original(timesheet.get_timesheet_detail_rate, **kwargs)


@frappe.whitelist()
def make_sales_invoice(**kwargs):
	_require_rates()
	return _original(timesheet.make_sales_invoice, **kwargs)


def rederive_timesheet_rates(doc, method=None) -> None:
	"""Timesheet validate, after ERPNext's own: rates come from Activity Cost for other jobs."""
	if sees_rates():
		return
	for row in doc.time_logs:
		row.costing_rate = 0
		row.billing_rate = 0
	doc.update_cost()
	doc.calculate_total_amounts()
	doc.calculate_percentage_billed()
