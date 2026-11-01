"""Likely demand by role from open deals (capacity plan sections 3 and 7, [P4-32]).

For Sales, who sees the likely line but no people, bookings or availability.
Hours come from capacity.likely_demand and never count as confirmed demand.
"""

import frappe
from frappe import _
from frappe.utils import cint, nowdate

from vellox_agency.capacity import likely_demand

DEFAULT_WEEKS = 8
MAX_REPORT_WEEKS = 26


def execute(filters=None):
	filters = frappe._dict(filters or {})
	weeks = min(max(cint(filters.weeks) or DEFAULT_WEEKS, 1), MAX_REPORT_WEEKS)
	rows = [
		{"role": role, **week}
		for role, role_weeks in sorted(likely_demand(filters.from_date or nowdate(), weeks).items())
		for week in role_weeks
	]
	return _columns(), rows


def _columns():
	return [
		{"fieldname": "role", "label": _("Role"), "fieldtype": "Data", "width": 160},
		{"fieldname": "week_start", "label": _("Week of"), "fieldtype": "Date", "width": 110},
		{"fieldname": "likely_hours", "label": _("Likely h"), "fieldtype": "Float", "width": 100},
	]
