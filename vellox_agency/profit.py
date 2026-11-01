"""Budget used, forecast and profit per project (capacity plan sections 5 and 6, [P4-33]).

contract value  = the project's quotation + submitted amendment quotations of
                  approved change requests (net totals)
budget          = those quotations' estimates: hours x rates + vendor cost
time cost       = submitted timesheet rows' costing amounts
external cost   = submitted Purchase Invoice rows + approved Expense Claims for the project
cost to date    = time cost + external cost
remaining cost  = open tasks' remaining hours x the assignee's cost rate for the
                  task's role (the role's default rate when unassigned)
                  + quoted vendor cost not yet spent
forecast cost   = cost to date + remaining cost (EAC)
budget used %   = cost to date / budget x 100
expected margin = (contract value - forecast cost) / contract value x 100
margin drift    = expected margin - the margin frozen on the project from its quote

Amounts are USD at each document's own date (owner, D7); remaining hours use
today's rate. Overhead is left out (D6). Only Finance and the Agency Manager
see amounts; the daily refresh stores the percentages and colour on Project
for Project Managers and Operations (section 7).
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from vellox_agency.estimate import _parse_hours

REPORTING_CURRENCY = "USD"
AMBER_MARGIN = 25  # expected margin under this many percent
AMBER_DRIFT = -10  # or more than this many points below the quote
RED_MARGIN = 10  # expected margin under this many percent, or forecast over the price
CHANGE_REQUEST_COUNTED = ("Approved", "Implemented", "Closed")
CLOSED_TASK_STATUSES = ("Completed", "Cancelled", "Template")

# Read by Project Managers, Operations, Finance and the Agency Manager, not by
# team members (section 7). ERPNext uses Project levels 0 and 1; [P4-31] uses 2.
PROFIT_PERMLEVEL = 3
PROFIT_READERS = ("Vellox Project Manager", "Vellox Operations", "Vellox Finance", "Agency Manager")
PROFIT_FIELDS = [
	{
		"fieldname": "custom_vellox_profit_section",
		"label": "Profit Health",
		"fieldtype": "Section Break",
		"insert_after": "custom_vellox_expected_margin_percent",
		"collapsible": 1,
	},
	{
		"fieldname": "custom_vellox_profit_signal",
		"label": "Profit Signal",
		"fieldtype": "Select",
		"options": "\nGreen\nAmber\nRed",
		"insert_after": "custom_vellox_profit_section",
	},
	{
		"fieldname": "custom_vellox_budget_used",
		"label": "Budget Used %",
		"fieldtype": "Percent",
		"insert_after": "custom_vellox_profit_signal",
	},
	{
		"fieldname": "custom_vellox_margin_drift",
		"label": "Margin Drift (points)",
		"fieldtype": "Float",
		"precision": "1",
		"insert_after": "custom_vellox_budget_used",
		"description": "Expected margin now minus the margin frozen from the quote.",
	},
	{
		"fieldname": "custom_vellox_profit_checked_on",
		"label": "Profit Checked On",
		"fieldtype": "Date",
		"insert_after": "custom_vellox_margin_drift",
	},
]
STORED = (
	"custom_vellox_profit_signal",
	"custom_vellox_budget_used",
	"custom_vellox_margin_drift",
	"custom_vellox_profit_checked_on",
)


def setup_profit_fields() -> None:
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
	from frappe.permissions import add_permission, setup_custom_perms, update_permission_property

	fields = [
		{**field, "read_only": 1, "no_copy": 1, "permlevel": PROFIT_PERMLEVEL}
		for field in PROFIT_FIELDS
		if field["fieldtype"] != "Section Break"
	]
	create_custom_fields(
		{
			"Project": [PROFIT_FIELDS[0], *fields],
			"Task": [
				{
					"fieldname": "custom_vellox_remaining_hours",
					"label": "Remaining Hours",
					"fieldtype": "Float",
					"insert_after": "expected_time",
					"description": "Hours still needed to finish, kept up to date by the project manager.",
				}
			],
		},
		update=True,
	)
	for role in PROFIT_READERS:
		filters = {"parent": "Project", "role": role, "permlevel": PROFIT_PERMLEVEL, "if_owner": 0}
		if frappe.db.get_value("Custom DocPerm", filters, "read"):
			continue
		setup_custom_perms("Project")
		if not frappe.db.exists("Custom DocPerm", filters):
			add_permission("Project", role, PROFIT_PERMLEVEL)
		update_permission_property("Project", role, PROFIT_PERMLEVEL, "read", 1, validate=False)
	frappe.clear_cache(doctype="Project")


def profit_signal(expected_margin, margin_drift, forecast_cost, contract_value) -> str:
	"""Owner-approved thresholds (section 5)."""
	if flt(expected_margin) < RED_MARGIN or flt(forecast_cost) > flt(contract_value):
		return "Red"
	if flt(expected_margin) < AMBER_MARGIN or (margin_drift is not None and flt(margin_drift) < AMBER_DRIFT):
		return "Amber"
	return "Green"


def project_profit(project: str) -> frappe._dict:
	return projects_profit([project])[project]


def projects_profit(projects: list[str]) -> dict[str, frappe._dict]:
	"""Figures for several projects, read with a fixed number of queries."""
	if not projects:
		return {}
	info = {
		p.name: p
		for p in frappe.get_all(
			"Project",
			filters={"name": ["in", projects]},
			fields=["name", "company", "custom_vellox_quotation", "custom_vellox_expected_margin_percent"],
		)
	}
	quotes = _quotations(info)
	time_cost = _time_cost(list(info))
	external = _external_cost(list(info))
	remaining = _remaining_hours_cost(list(info))
	result = {}
	for name, project in info.items():
		q = quotes.get(name, frappe._dict(contract=0, labour=0, vendor=0))
		currency = _company_currency(project.company)
		p = frappe._dict(project=name)
		p.contract_value = round(q.contract, 2)
		p.budget = round(q.labour + q.vendor, 2)
		p.frozen_margin = project.custom_vellox_expected_margin_percent
		p.time_cost = round(time_cost.get(name, 0), 2)
		p.external_cost = round(flt(external.get(name)), 2)
		p.cost_to_date = round(p.time_cost + p.external_cost, 2)
		task_cost, p.unpriced_hours = remaining.get(name, (0, 0))
		vendor_to_come = max(0, q.vendor - p.external_cost)
		p.remaining_cost = round(_to_usd(task_cost, currency, nowdate()) + vendor_to_come, 2)
		p.forecast_cost = round(p.cost_to_date + p.remaining_cost, 2)
		p.budget_used = round(p.cost_to_date / p.budget * 100, 2) if p.budget else None
		if p.contract_value:
			p.expected_margin = round((p.contract_value - p.forecast_cost) / p.contract_value * 100, 2)
			p.margin_drift = (
				round(p.expected_margin - flt(p.frozen_margin), 2) if p.frozen_margin is not None else None
			)
			p.signal = profit_signal(p.expected_margin, p.margin_drift, p.forecast_cost, p.contract_value)
		else:
			p.expected_margin = p.margin_drift = p.signal = None  # nothing quoted yet
		result[name] = p
	return result


def profit_or_errors(projects: list[str]) -> tuple[dict[str, frappe._dict], dict[str, str]]:
	"""Figures per project; a project whose amounts cannot be converted gets an error instead."""
	try:
		return projects_profit(projects), {}
	except frappe.ValidationError:
		pass  # find the projects at fault, one by one
	results, errors = {}, {}
	for name in projects:
		try:
			results[name] = project_profit(name)
		except frappe.ValidationError as error:
			errors[name] = str(error)
	return results, errors


def refresh_project_profit() -> None:
	"""Daily: store the percentages and colour on every open quoted project."""
	names = frappe.get_all(
		"Project", filters={"status": "Open", "custom_vellox_quotation": ["is", "set"]}, pluck="name"
	)
	results, errors = profit_or_errors(names)
	today = nowdate()
	for name, p in results.items():
		# Float columns cannot be empty; a blank signal says there is nothing to measure yet.
		values = (p.signal or "", flt(p.budget_used), flt(p.margin_drift), today)
		frappe.db.set_value("Project", name, dict(zip(STORED, values, strict=True)), update_modified=False)
	for name, message in errors.items():
		frappe.log_error(title=_("Vellox profit check skipped {0}").format(name), message=message)


def _company_currency(company: str) -> str:
	return frappe.get_cached_value("Company", company, "default_currency") if company else REPORTING_CURRENCY


def _to_usd(amount, currency, day) -> float:
	if not amount or not currency or currency == REPORTING_CURRENCY:
		return flt(amount)
	from erpnext.setup.utils import get_exchange_rate

	rate = get_exchange_rate(currency, REPORTING_CURRENCY, getdate(day))
	if not rate:
		raise frappe.ValidationError(
			_("No {0} to {1} exchange rate for {2}. Add a Currency Exchange record.").format(
				currency, REPORTING_CURRENCY, frappe.format(getdate(day), "Date")
			)
		)
	return flt(amount) * flt(rate)


def _quotations(projects: dict) -> dict[str, frappe._dict]:
	"""Contract value and budget per project from its quotes (original + approved amendments)."""
	quote_project = {
		p.custom_vellox_quotation: name for name, p in projects.items() if p.custom_vellox_quotation
	}
	for row in frappe.get_all(
		"Vellox Change Request",
		filters={
			"project": ["in", list(projects)],
			"status": ["in", CHANGE_REQUEST_COUNTED],
			"amendment_quotation": ["is", "set"],
		},
		fields=["project", "amendment_quotation"],
	):
		quote_project[row.amendment_quotation] = row.project
	result = defaultdict(lambda: frappe._dict(contract=0, labour=0, vendor=0))
	if not quote_project:
		return result
	for quote in frappe.get_all(
		"Quotation",
		filters={"name": ["in", list(quote_project)], "docstatus": 1},
		fields=[
			"name",
			"currency",
			"transaction_date",
			"net_total",
			"custom_vellox_estimate_hours",
			"custom_vellox_vendor_cost",
		],
	):
		totals = result[quote_project[quote.name]]
		labour = sum(
			flt(r.get("hours")) * flt(r.get("rate")) for r in _parse_hours(quote.custom_vellox_estimate_hours)
		)
		totals.contract += _to_usd(quote.net_total, quote.currency, quote.transaction_date)
		totals.labour += _to_usd(labour, quote.currency, quote.transaction_date)
		totals.vendor += _to_usd(quote.custom_vellox_vendor_cost, quote.currency, quote.transaction_date)
	return result


def _time_cost(projects: list[str]) -> dict[str, float]:
	"""Submitted timesheet costing amounts (company currency) per project, in USD."""
	ts = frappe.qb.DocType("Timesheet")
	row = frappe.qb.DocType("Timesheet Detail")
	sums = (
		frappe.qb.from_(row)
		.join(ts)
		.on(row.parent == ts.name)
		.select(
			row.project,
			ts.company,
			ts.start_date,
			frappe.query_builder.functions.Sum(row.base_costing_amount),
		)
		.where((ts.docstatus == 1) & row.project.isin(projects))
		.groupby(row.project, ts.company, ts.start_date)
	).run()
	result = defaultdict(float)
	for project, company, day, amount in sums:
		result[project] += _to_usd(amount, _company_currency(company), day)
	return result


def _external_cost(projects: list[str]) -> dict[str, float]:
	"""Vendor invoices and approved expense claims per project, in USD."""
	from frappe.query_builder.functions import Sum

	result = defaultdict(float)
	pi = frappe.qb.DocType("Purchase Invoice")
	item = frappe.qb.DocType("Purchase Invoice Item")
	invoices = (
		frappe.qb.from_(item)
		.join(pi)
		.on(item.parent == pi.name)
		.select(item.project, pi.company, pi.posting_date, Sum(item.base_net_amount))
		.where((pi.docstatus == 1) & item.project.isin(projects))
		.groupby(item.project, pi.company, pi.posting_date)
	).run()
	claim = frappe.qb.DocType("Expense Claim")
	claims = (
		frappe.qb.from_(claim)
		.select(claim.project, claim.company, claim.posting_date, Sum(claim.total_sanctioned_amount))
		.where((claim.docstatus == 1) & (claim.approval_status == "Approved") & claim.project.isin(projects))
		.groupby(claim.project, claim.company, claim.posting_date)
	).run()
	for project, company, day, amount in (*invoices, *claims):
		result[project] += _to_usd(amount, _company_currency(company), day)
	return result


def _remaining_hours_cost(projects: list[str]) -> dict[str, tuple[float, float]]:
	"""(cost in company currency, hours without a rate) of open tasks' remaining hours."""
	tasks = frappe.get_all(
		"Task",
		filters={
			"project": ["in", projects],
			"status": ["not in", CLOSED_TASK_STATUSES],
			"custom_vellox_remaining_hours": [">", 0],
		},
		fields=["project", "custom_vellox_default_role", "custom_vellox_remaining_hours", "_assign"],
	)
	if not tasks:
		return {}
	users = {_first_assignee(t._assign) for t in tasks} - {None}
	employee_of = (
		dict(
			frappe.get_all(
				"Employee", filters={"user_id": ["in", list(users)]}, fields=["user_id", "name"], as_list=True
			)
		)
		if users
		else {}
	)
	roles = {t.custom_vellox_default_role for t in tasks} - {None, ""}
	person_rate = {
		(r.employee, r.activity_type): flt(r.costing_rate)
		for r in frappe.get_all(
			"Activity Cost",
			filters={
				"employee": ["in", list(employee_of.values()) or [""]],
				"activity_type": ["in", list(roles) or [""]],
			},
			fields=["employee", "activity_type", "costing_rate"],
		)
	}
	role_rate = dict(
		frappe.get_all(
			"Activity Type",
			filters={"name": ["in", list(roles) or [""]]},
			fields=["name", "costing_rate"],
			as_list=True,
		)
	)
	result = defaultdict(lambda: [0.0, 0.0])
	for task in tasks:
		hours = flt(task.custom_vellox_remaining_hours)
		employee = employee_of.get(_first_assignee(task._assign))
		rate = person_rate.get((employee, task.custom_vellox_default_role)) or flt(
			role_rate.get(task.custom_vellox_default_role)
		)
		if rate:
			result[task.project][0] += hours * rate
		else:
			result[task.project][1] += hours
	return {project: tuple(values) for project, values in result.items()}


def _first_assignee(assign: str | None) -> str | None:
	users = frappe.parse_json(assign) if assign else []
	return users[0] if users else None
