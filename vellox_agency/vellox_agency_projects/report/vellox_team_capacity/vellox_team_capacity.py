"""Team capacity per person and week, plus the likely line by role (capacity plan section 3, [P4-32]).

Team members and staff see only their own rows and no likely line (section 7).
"""

import frappe
from frappe import _
from frappe.utils import cint, nowdate

from vellox_agency import security
from vellox_agency.capacity import likely_demand, weekly_capacity

DEFAULT_WEEKS = 8
MAX_REPORT_WEEKS = 26


def execute(filters=None):
	filters = frappe._dict(filters or {})
	user = frappe.session.user
	if security.access_level("Vellox Resource Allocation", user) in (security.NONE, security.LINK):
		frappe.throw(_("Your job does not give access to team capacity."), frappe.PermissionError)
	weeks = min(max(cint(filters.weeks) or DEFAULT_WEEKS, 1), MAX_REPORT_WEEKS)
	from_date = filters.from_date or nowdate()
	team_scoped = security._team_scoped(user)

	employee_filters = {"status": "Active"}
	if team_scoped:
		employee_filters["user_id"] = user
	rows = []
	for person in frappe.get_all(
		"Employee", filters=employee_filters, fields=["name", "employee_name", "designation"], order_by="employee_name"
	):
		base = {"employee": person.name, "employee_name": person.employee_name, "designation": person.designation}
		try:
			weeks_rows = weekly_capacity(person.name, from_date, weeks)
		except frappe.ValidationError as error:
			rows.append({**base, "note": str(error)})
			continue
		rows.extend({**base, **week} for week in weeks_rows)

	if not team_scoped:
		for role, role_weeks in sorted(likely_demand(from_date, weeks).items()):
			rows.extend(
				{"employee_name": _("Likely: {0}").format(role), "designation": role, **week} for week in role_weeks
			)
	return _columns(), rows


def _columns():
	return [
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "designation", "label": _("Role"), "fieldtype": "Data", "width": 130},
		{"fieldname": "week_start", "label": _("Week of"), "fieldtype": "Date", "width": 100},
		{"fieldname": "available_hours", "label": _("Available h"), "fieldtype": "Float", "width": 100},
		{"fieldname": "target_hours", "label": _("Target h"), "fieldtype": "Float", "width": 90},
		{"fieldname": "confirmed_hours", "label": _("Booked h"), "fieldtype": "Float", "width": 90},
		{"fieldname": "free_hours", "label": _("Free h"), "fieldtype": "Float", "width": 80},
		{"fieldname": "overbooked_hours", "label": _("Overbooked h"), "fieldtype": "Float", "width": 110},
		{"fieldname": "likely_hours", "label": _("Likely h"), "fieldtype": "Float", "width": 90},
		{"fieldname": "note", "label": _("Note"), "fieldtype": "Data", "width": 260},
	]
