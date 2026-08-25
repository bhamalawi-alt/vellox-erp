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
		{"fieldname": "metric", "label": _("Metric"), "fieldtype": "Data", "width": 200},
		{"fieldname": "value", "label": _("Value"), "fieldtype": "Float", "width": 120},
		{"fieldname": "as_of", "label": _("As Of"), "fieldtype": "Date", "width": 110},
	]


def get_data(filters):
	as_of = filters.get("as_of_date") or frappe.utils.today()
	total_invoiced = frappe.db.sql(
		"""select coalesce(sum(total), 0) from `tabAgency Invoice`""", as_list=1
	)[0][0]
	outstanding = frappe.db.sql(
		"""select coalesce(sum(total), 0) from `tabAgency Invoice`
		where status not in ('Paid', 'Cancelled')""", as_list=1
	)[0][0]
	budget = frappe.db.sql(
		"""select coalesce(sum(budget), 0) from `tabAgency Campaign`""", as_list=1
	)[0][0]
	spent = frappe.db.sql(
		"""select coalesce(sum(spend), 0) from `tabMedia Spend`""", as_list=1
	)[0][0]
	total_hours = frappe.db.sql(
		"""select coalesce(sum(total_hours), 0) from `tabAgency Timesheet`""", as_list=1
	)[0][0]
	capacity = frappe.db.sql(
		"""select coalesce(sum(available_hours), 0) from `tabCapacity Plan`""", as_list=1
	)[0][0]

	metrics = [
		("Clients", count_doctype("Client Account")),
		("Engagements", count_doctype("Engagement")),
		("Active Projects", count_active_projects()),
		("Live Campaigns", count_live_campaigns()),
		("Production Jobs Open", count_open_jobs()),
		("Total Invoiced", total_invoiced),
		("Outstanding Invoices", outstanding),
		("Total Media Budget", budget),
		("Total Media Spend", spent),
		("Tracked Hours", total_hours),
		("Scheduled Capacity Hours", capacity),
	]

	data = []
	for label, value in metrics:
		data.append({"metric": label, "value": flt(value, 2), "as_of": as_of})
	return data


def count_doctype(doctype):
	return frappe.db.count(doctype)


def count_active_projects():
	return frappe.db.count(
		"Agency Project",
		filters={"status": ["not in", ["Completed", "Archived"]]},
	)


def count_live_campaigns():
	return frappe.db.count("Agency Campaign", filters={"campaign_status": "Live"})


def count_open_jobs():
	return frappe.db.count(
		"Production Job",
		filters={"status": ["not in", ["Done", "Cancelled"]]},
	)


def get_chart(data):
	values = {d["metric"]: flt(d["value"]) for d in data}
	return {
		"data": {
			"labels": list(values.keys()),
			"datasets": [{"name": "Agency KPI", "values": list(values.values())}],
		},
		"type": "bar",
	}
