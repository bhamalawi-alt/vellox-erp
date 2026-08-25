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
		{"fieldname": "invoice", "label": _("Invoice"), "fieldtype": "Link", "options": "Agency Invoice", "width": 150},
		{"fieldname": "invoice_date", "label": _("Invoice Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "due_date", "label": _("Due Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "client_account", "label": _("Client"), "fieldtype": "Link", "options": "Client Account", "width": 150},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "total", "label": _("Total"), "fieldtype": "Currency", "options": "currency", "width": 110},
		{"fieldname": "days_overdue", "label": _("Days Overdue"), "fieldtype": "Int", "width": 100},
	]


def get_data(filters):
	conditions = []
	values = {}
	if filters.get("from_date"):
		conditions.append("i.invoice_date >= %(from_date)s")
		values["from_date"] = filters.get("from_date")
	if filters.get("to_date"):
		conditions.append("i.invoice_date <= %(to_date)s")
		values["to_date"] = filters.get("to_date")
	if filters.get("status"):
		conditions.append("i.status = %(status)s")
		values["status"] = filters.get("status")
	if filters.get("client_account"):
		conditions.append("i.client_account = %(client_account)s")
		values["client_account"] = filters.get("client_account")
	where = " and ".join(conditions)
	if where:
		where = "where " + where

	rows = frappe.db.sql(
		f"""
		select
			i.name as invoice,
			i.invoice_date,
			i.due_date,
			i.client_account,
			i.status,
			i.total,
			i.currency,
			datediff(coalesce(i.due_date, curdate()), curdate()) as days_overdue
		from `tabAgency Invoice` i
		{where}
		order by i.invoice_date desc
		""",
		values,
		as_dict=1,
	)

	data = []
	for r in rows:
		overdue = flt(r.days_overdue)
		r.days_overdue = int(overdue) if overdue < 0 and r.get("status") not in ("Paid", "Cancelled") else 0
		data.append(r)
	return data


def get_chart(data):
	status_count = {}
	for d in data:
		status_count[d["status"]] = status_count.get(d["status"], 0) + 1
	return {
		"data": {
			"labels": list(status_count.keys()),
			"datasets": [{"name": _("Invoices by Status"), "values": list(status_count.values())}],
		},
		"type": "pie",
	}
