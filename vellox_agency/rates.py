"""Rates follow job access ([P4-31]).

ERPNext's Timesheet form fetches a person's cost and bill rate through a
whitelisted call that answers anyone. Jobs without access to Activity Cost get
zero rates; the Timesheet still saves the right cost, because the server
looks the rate up again on save and Frappe drops rate values a user may not
write.
"""

import frappe
from erpnext.projects.doctype.timesheet import timesheet

from vellox_agency import security


def sees_rates(user: str | None = None) -> bool:
	return security.access_level("Activity Cost", user or frappe.session.user) in (None, security.VIEW, security.EDIT)


@frappe.whitelist()
def get_activity_cost(employee=None, activity_type=None, currency=None):
	rate = timesheet.get_activity_cost(employee=employee, activity_type=activity_type, currency=currency) or {}
	if sees_rates():
		return rate
	return {**rate, "costing_rate": 0, "billing_rate": 0}
