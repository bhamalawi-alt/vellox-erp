# Copyright (c) 2026, Vellox Team and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters or {})
	chart = get_chart(data)
	return columns, data, None, chart, None


def get_columns():
	return [
		{"fieldname": "job_name", "label": _("Job"), "fieldtype": "Link", "options": "Production Job", "width": 200},
		{"fieldname": "client_account", "label": _("Client"), "fieldtype": "Link", "options": "Client Account", "width": 150},
		{"fieldname": "job_type", "label": _("Type"), "fieldtype": "Data", "width": 120},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
		{"fieldname": "priority", "label": _("Priority"), "fieldtype": "Data", "width": 90},
		{"fieldname": "assigned_to", "label": _("Assigned To"), "fieldtype": "Link", "options": "User", "width": 150},
		{"fieldname": "due_date", "label": _("Due Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "overdue_days", "label": _("Overdue (days)"), "fieldtype": "Int", "width": 100},
	]


def get_data(filters):
	conditions = []
	values = {}
	if filters.get("status"):
		conditions.append("p.status = %(status)s")
		values["status"] = filters.get("status")
	if filters.get("priority"):
		conditions.append("p.priority = %(priority)s")
		values["priority"] = filters.get("priority")
	if filters.get("assigned_to"):
		conditions.append("p.assigned_to = %(assigned_to)s")
		values["assigned_to"] = filters.get("assigned_to")
	where = " and ".join(conditions)
	if where:
		where = "where " + where

	rows = frappe.db.sql(
		f"""
		select
			p.name as job_name,
			p.client_account,
			p.job_type,
			p.status,
			p.priority,
			p.assigned_to,
			p.due_date,
			datediff(coalesce(p.due_date, curdate()), curdate()) as overdue_days
		from `tabProduction Job` p
		{where}
		order by p.status, p.due_date
		""",
		values,
		as_dict=1,
	)

	data = []
	for r in rows:
		overdue = flt(r.overdue_days)
		r.overdue_days = int(overdue) if overdue < 0 and r.get("status") not in ("Done", "Cancelled") else 0
		data.append(r)
	return data


def get_chart(data):
	status_count = {}
	for d in data:
		status_count[d["status"]] = status_count.get(d["status"], 0) + 1
	return {
		"data": {
			"labels": list(status_count.keys()),
			"datasets": [{"name": _("Jobs by Status"), "values": list(status_count.values())}],
		},
		"type": "pie",
	}
