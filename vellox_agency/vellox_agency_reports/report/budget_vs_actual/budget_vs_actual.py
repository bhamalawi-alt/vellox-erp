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
		{"fieldname": "campaign", "label": _("Campaign"), "fieldtype": "Link", "options": "Agency Campaign", "width": 200},
		{"fieldname": "client_account", "label": _("Client"), "fieldtype": "Link", "options": "Client Account", "width": 150},
		{"fieldname": "media_platform", "label": _("Platform"), "fieldtype": "Data", "width": 140},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "budget", "label": _("Budget"), "fieldtype": "Currency", "options": "currency", "width": 110},
		{"fieldname": "spent", "label": _("Actual Spend"), "fieldtype": "Currency", "options": "currency", "width": 110},
		{"fieldname": "remaining", "label": _("Remaining"), "fieldtype": "Currency", "options": "currency", "width": 110},
		{"fieldname": "utilization_pct", "label": _("Utilization %"), "fieldtype": "Percent", "width": 100},
	]


def get_data(filters):
	conditions = []
	values = {}
	if filters.get("from_date"):
		conditions.append("c.start_date >= %(from_date)s")
		values["from_date"] = filters.get("from_date")
	if filters.get("to_date"):
		conditions.append("c.end_date <= %(to_date)s")
		values["to_date"] = filters.get("to_date")
	if filters.get("client_account"):
		conditions.append("c.client_account = %(client_account)s")
		values["client_account"] = filters.get("client_account")
	where = " and ".join(conditions)
	if where:
		where = "where " + where

	rows = frappe.db.sql(
		f"""
		select
			c.name as campaign,
			c.client_account,
			c.media_platform,
			c.campaign_status as status,
			c.currency,
			c.budget,
			coalesce((
				select sum(s.spend)
				from `tabMedia Spend` s
				where s.parent = c.name
			), 0) as spent
		from `tabAgency Campaign` c
		{where}
		order by c.creation desc
		""",
		values,
		as_dict=1,
	)

	data = []
	for r in rows:
		spent = flt(r.spent)
		budget = flt(r.budget)
		r.spent = spent
		r.remaining = budget - spent
		r.utilization_pct = (spent / budget * 100) if budget else 0
		data.append(r)
	return data


def get_chart(data):
	labels = [d["campaign"] for d in data]
	budget_values = [flt(d["budget"]) for d in data]
	spent_values = [flt(d["spent"]) for d in data]
	return {
		"data": {
			"labels": labels,
			"datasets": [
				{"name": _("Budget"), "values": budget_values},
				{"name": _("Actual"), "values": spent_values},
			],
		},
		"type": "bar",
	}
