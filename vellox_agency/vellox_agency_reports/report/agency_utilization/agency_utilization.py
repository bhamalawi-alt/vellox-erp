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
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "User", "width": 180},
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link", "options": "Agency Project", "width": 180},
		{"fieldname": "client_account", "label": _("Client"), "fieldtype": "Link", "options": "Client Account", "width": 150},
		{"fieldname": "total_hours", "label": _("Total Hours"), "fieldtype": "Float", "width": 100},
		{"fieldname": "billable_hours", "label": _("Billable Hours"), "fieldtype": "Float", "width": 110},
		{"fieldname": "non_billable_hours", "label": _("Non-Billable Hours"), "fieldtype": "Float", "width": 130},
		{"fieldname": "utilization_pct", "label": _("Utilization %"), "fieldtype": "Percent", "width": 100},
	]


def get_data(filters):
	conditions = []
	values = {}
	if filters.get("from_date"):
		conditions.append("t.timesheet_date >= %(from_date)s")
		values["from_date"] = filters.get("from_date")
	if filters.get("to_date"):
		conditions.append("t.timesheet_date <= %(to_date)s")
		values["to_date"] = filters.get("to_date")
	if filters.get("employee"):
		conditions.append("t.employee = %(employee)s")
		values["employee"] = filters.get("employee")
	where = " and ".join(conditions)
	if where:
		where = "where " + where

	rows = frappe.db.sql(
		f"""
		select
			t.employee,
			t.project,
			t.client_account,
			coalesce(sum(t.total_hours), 0) as total_hours,
			coalesce(sum(t.billable_hours), 0) as billable_hours
		from `tabAgency Timesheet` t
		{where}
		group by t.employee, t.project, t.client_account
		order by t.employee
		""",
		values,
		as_dict=1,
	)

	data = []
	for r in rows:
		total = flt(r.total_hours)
		billable = flt(r.billable_hours)
		r.non_billable_hours = total - billable
		r.utilization_pct = (billable / total * 100) if total else 0
		data.append(r)
	return data


def get_chart(data):
	labels = [f"{d['employee']} / {d['project']}" for d in data]
	values = [flt(d["total_hours"]) for d in data]
	return {
		"data": {"labels": labels, "datasets": [{"name": _("Hours"), "values": values}]},
		"type": "bar",
	}
