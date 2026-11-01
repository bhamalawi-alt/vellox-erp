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

Amounts are USD at each document's own date (owner, D7), from the site's
Currency Exchange records only (never an outside service); remaining hours use
today's rate. Overhead is left out (D6). Only Finance and the Agency Manager
see amounts. The daily refresh stores the percentages and colour on Project for
Operations, Finance and the Agency Manager; Project Managers see them for their
own projects in the Vellox Project Profit report (section 7).
"""

import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

REPORTING_CURRENCY = "USD"
AMBER_MARGIN = 25  # expected margin under this many percent
AMBER_DRIFT = -10  # or more than this many points below the quote
RED_MARGIN = 10  # expected margin under this many percent, or forecast over the price
# Change requests whose amendment quote counts (owner, 2026-11-01, [P4-35]):
# Approved and Implemented ones, and Closed ones that were implemented first.
# A request closed straight from Approved was withdrawn.
CHANGE_REQUEST_COUNTED = ("Approved", "Implemented")
CLOSED_TASK_STATUSES = ("Completed", "Cancelled", "Template")

# Read by Operations, Finance and the Agency Manager, not by team members.
# Project Managers edit every project, so they would see every project's colour
# here; they read their own projects' figures in the report instead (section 7).
# ERPNext uses Project levels 0 and 1; [P4-31] uses 2.
PROFIT_PERMLEVEL = 3
PROFIT_READERS = ("Vellox Operations", "Vellox Finance", "Agency Manager")
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
		"description": "Blank when there is nothing to measure yet, or the last check could not convert an amount.",
	},
	{
		"fieldname": "custom_vellox_budget_used",
		"label": "Budget Used %",
		"fieldtype": "Percent",
		"insert_after": "custom_vellox_profit_signal",
		"depends_on": "eval:doc.custom_vellox_profit_signal",
	},
	{
		"fieldname": "custom_vellox_margin_drift",
		"label": "Margin Drift (points)",
		"fieldtype": "Float",
		"precision": "1",
		"insert_after": "custom_vellox_budget_used",
		"depends_on": "eval:doc.custom_vellox_profit_signal",
		"description": "Expected margin now minus the margin frozen from the quote.",
	},
	{
		"fieldname": "custom_vellox_profit_checked_on",
		"label": "Profit Checked On",
		"fieldtype": "Date",
		"insert_after": "custom_vellox_margin_drift",
	},
]
# Task Remaining Hours feeds the forecast: everyone who sees the task reads it,
# only Project Managers, Operations and the Agency Manager change it ([P4-35]).
# Task level 1 holds the money fields ([P4-31]).
REMAINING_HOURS_PERMLEVEL = 2
REMAINING_HOURS_READERS = ("Projects User",)
REMAINING_HOURS_WRITERS = ("Vellox Project Manager", "Vellox Operations", "Agency Manager", "System Manager")
INTERNAL_FIELD = {
	"fieldname": "custom_vellox_internal",
	"label": "Internal Project",
	"fieldtype": "Check",
	"insert_after": "custom_vellox_quotation",
	"description": "Agency work for no client: its hours count as worked, not billable.",
}
STORED = (
	"custom_vellox_profit_signal",
	"custom_vellox_budget_used",
	"custom_vellox_margin_drift",
	"custom_vellox_profit_checked_on",
)


def setup_profit_fields() -> None:
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	fields = [
		{**field, "read_only": 1, "no_copy": 1, "permlevel": PROFIT_PERMLEVEL} for field in PROFIT_FIELDS
	]
	create_custom_fields(
		{
			"Project": [INTERNAL_FIELD, *fields],
			"Task": [
				{
					"fieldname": "custom_vellox_remaining_hours",
					"label": "Remaining Hours",
					"fieldtype": "Float",
					"insert_after": "expected_time",
					"permlevel": REMAINING_HOURS_PERMLEVEL,
					"description": "Hours still needed to finish, kept up to date by the project manager.",
				}
			],
		},
		update=True,
	)
	for role in PROFIT_READERS:
		_grant("Project", role, PROFIT_PERMLEVEL, "read")
	for role in REMAINING_HOURS_READERS:
		_grant("Task", role, REMAINING_HOURS_PERMLEVEL, "read")
	for role in REMAINING_HOURS_WRITERS:
		_grant("Task", role, REMAINING_HOURS_PERMLEVEL, "read")
		_grant("Task", role, REMAINING_HOURS_PERMLEVEL, "write")
	frappe.clear_cache(doctype="Project")
	frappe.clear_cache(doctype="Task")


def _grant(doctype: str, role: str, permlevel: int, right: str) -> None:
	"""Give `role` `right` at `permlevel` through Custom DocPerm, once."""
	from frappe.permissions import add_permission, setup_custom_perms, update_permission_property

	filters = {"parent": doctype, "role": role, "permlevel": permlevel, "if_owner": 0}
	if frappe.db.get_value("Custom DocPerm", filters, right):
		return
	setup_custom_perms(doctype)
	if not frappe.db.exists("Custom DocPerm", filters):
		add_permission(doctype, role, permlevel)
	update_permission_property(doctype, role, permlevel, right, 1, validate=False)


def profit_signal(expected_margin, margin_drift, forecast_cost, contract_value) -> str:
	"""Owner-approved thresholds (section 5)."""
	if flt(expected_margin) < RED_MARGIN or flt(forecast_cost) > flt(contract_value):
		return "Red"
	if flt(expected_margin) < AMBER_MARGIN or (margin_drift is not None and flt(margin_drift) < AMBER_DRIFT):
		return "Amber"
	return "Green"


def project_profit(project: str) -> frappe._dict:
	"""One project's figures; raises ValidationError when an amount cannot be converted."""
	results, errors = projects_profit([project])
	if project in errors:
		raise frappe.ValidationError(errors[project])
	return results[project]


def projects_profit(projects: list[str]) -> tuple[dict[str, frappe._dict], dict[str, str]]:
	"""Figures per project, and an error message for each project that cannot be worked out.

	The records are read with a fixed number of queries; currency rates add one
	query per currency and date, only for amounts that are not in USD.
	"""
	if not projects:
		return {}, {}
	info = {
		p.name: p
		for p in frappe.get_all(
			"Project",
			filters={"name": ["in", projects]},
			fields=["name", "company", "custom_vellox_quotation", "custom_vellox_expected_margin_percent"],
		)
	}
	names = list(info)
	quotes = _quotations(info)
	time_cost = _time_cost(names)
	invoices, claims = _external_cost(names)
	remaining = _remaining_hours_cost(names)
	rates = _Rates()
	results, errors = {}, {}
	for name, project in info.items():
		try:
			results[name] = _figures(
				project,
				quotes.get(name, []),
				time_cost.get(name, []),
				invoices.get(name, []),
				claims.get(name, []),
				remaining.get(name, (0, 0)),
				rates,
			)
		except frappe.ValidationError as error:
			errors[name] = str(error)
	return results, errors


def _figures(project, quotes, time_rows, invoice_rows, claim_rows, remaining, rates) -> frappe._dict:
	contract = labour = vendor = 0
	for quote in quotes:
		rate = rates.get(quote.currency, quote.transaction_date)
		contract += flt(quote.net_total) * rate
		labour += _estimate_labour(quote) * rate
		vendor += flt(quote.custom_vellox_vendor_cost) * rate
	company_currency = _company_currency(project.company)
	p = frappe._dict(project=project.name)
	p.contract_value = round(contract, 2)
	p.budget = round(labour + vendor, 2)
	p.frozen_margin = project.custom_vellox_expected_margin_percent
	p.time_cost = round(rates.total(time_rows), 2)
	invoiced = rates.total(invoice_rows)
	p.external_cost = round(invoiced + rates.total(claim_rows), 2)
	p.cost_to_date = round(p.time_cost + p.external_cost, 2)
	task_cost, p.unpriced_hours = remaining
	vendor_to_come = max(0, vendor - invoiced)  # only vendor invoices use up the quoted vendor cost
	p.remaining_cost = round(flt(task_cost) * rates.get(company_currency, nowdate()) + vendor_to_come, 2)
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
	return p


def refresh_project_profit() -> None:
	"""Daily: store the percentages and colour on every open quoted project."""
	names = frappe.get_all(
		"Project", filters={"status": "Open", "custom_vellox_quotation": ["is", "set"]}, pluck="name"
	)
	results, errors = projects_profit(names)
	today = nowdate()
	for name, p in results.items():
		# Float columns cannot be empty; the form hides them while the signal is blank.
		values = (p.signal or "", flt(p.budget_used), flt(p.margin_drift), today)
		frappe.db.set_value("Project", name, dict(zip(STORED, values, strict=True)), update_modified=False)
	for name, message in errors.items():
		# An old colour would look current: clear it until the check works again.
		frappe.db.set_value(
			"Project", name, dict(zip(STORED[:3], ("", 0, 0), strict=True)), update_modified=False
		)
		frappe.log_error(title=_("Vellox profit check skipped {0}").format(name), message=message)


class _Rates:
	"""Rates to USD from Currency Exchange records, read once per currency and date."""

	def __init__(self):
		self._cache = {}

	def get(self, currency: str | None, day) -> float:
		if not currency or currency == REPORTING_CURRENCY:
			return 1.0
		key = (currency, getdate(day))
		if key not in self._cache:
			self._cache[key] = self._lookup(*key)
		if not self._cache[key]:
			raise frappe.ValidationError(
				_("No {0} to {1} exchange rate on or before {2}. Add a Currency Exchange record.").format(
					currency, REPORTING_CURRENCY, frappe.format(key[1], "Date")
				)
			)
		return self._cache[key]

	def total(self, rows) -> float:
		return sum(flt(amount) * self.get(currency, day) for currency, day, amount in rows)

	@staticmethod
	def _lookup(currency: str, day) -> float:
		for from_currency, to_currency, invert in (
			(currency, REPORTING_CURRENCY, False),
			(REPORTING_CURRENCY, currency, True),
		):
			rate = frappe.get_all(
				"Currency Exchange",
				filters={"from_currency": from_currency, "to_currency": to_currency, "date": ["<=", day]},
				order_by="date desc",
				limit=1,
				pluck="exchange_rate",
			)
			if rate and flt(rate[0]):
				return 1 / flt(rate[0]) if invert else flt(rate[0])
		return 0.0


def _company_currency(company: str) -> str:
	return frappe.get_cached_value("Company", company, "default_currency") if company else REPORTING_CURRENCY


def _estimate_labour(quote) -> float:
	"""Hours x rates from a quote's estimate panel; bad data raises without a message dialog."""
	raw = quote.custom_vellox_estimate_hours
	try:
		rows = json.loads(raw) if isinstance(raw, str) and raw else (raw or [])
		return sum(flt(row.get("hours")) * flt(row.get("rate")) for row in rows)
	except (ValueError, TypeError, AttributeError):
		raise frappe.ValidationError(
			_("Quotation {0} has an unreadable estimate.").format(quote.name)
		) from None


def _quotations(projects: dict) -> dict[str, list]:
	"""Each project's submitted quotes: the original and approved change-request amendments."""
	quote_project = {
		p.custom_vellox_quotation: name for name, p in projects.items() if p.custom_vellox_quotation
	}
	for row in frappe.get_all(
		"Vellox Change Request",
		filters={"project": ["in", list(projects)], "amendment_quotation": ["is", "set"]},
		or_filters=[["status", "in", CHANGE_REQUEST_COUNTED], ["implemented_on", "is", "set"]],
		fields=["project", "amendment_quotation"],
	):
		quote_project[row.amendment_quotation] = row.project
	result = defaultdict(list)
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
		result[quote_project[quote.name]].append(quote)
	return result


def _by_project(sums) -> dict[str, list]:
	"""(project, company, date, amount) rows -> {project: [(currency, date, amount)]}."""
	result = defaultdict(list)
	for project, company, day, amount in sums:
		result[project].append((_company_currency(company), day, amount))
	return result


def _time_cost(projects: list[str]) -> dict[str, list]:
	"""Submitted timesheet costing amounts (company currency) per project and date."""
	from frappe.query_builder.functions import Sum

	ts = frappe.qb.DocType("Timesheet")
	row = frappe.qb.DocType("Timesheet Detail")
	return _by_project(
		(
			frappe.qb.from_(row)
			.join(ts)
			.on(row.parent == ts.name)
			.select(row.project, ts.company, ts.start_date, Sum(row.base_costing_amount))
			.where((ts.docstatus == 1) & row.project.isin(projects))
			.groupby(row.project, ts.company, ts.start_date)
		).run()
	)


def _external_cost(projects: list[str]) -> tuple[dict[str, list], dict[str, list]]:
	"""(vendor invoice rows, approved expense claim rows) per project and date."""
	from frappe.query_builder.functions import Sum

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
	# The claim's own project, as Frappe HR counts Project.total_expense_claim.
	claim = frappe.qb.DocType("Expense Claim")
	claims = (
		frappe.qb.from_(claim)
		.select(claim.project, claim.company, claim.posting_date, Sum(claim.total_sanctioned_amount))
		.where((claim.docstatus == 1) & (claim.approval_status == "Approved") & claim.project.isin(projects))
		.groupby(claim.project, claim.company, claim.posting_date)
	).run()
	return _by_project(invoices), _by_project(claims)


def _remaining_hours_cost(projects: list[str]) -> dict[str, tuple[float, float]]:
	"""(cost in company currency, hours without a rate) of open tasks' remaining hours."""
	tasks = frappe.get_all(
		"Task",
		filters={
			"project": ["in", projects],
			"status": ["not in", CLOSED_TASK_STATUSES],
			"custom_vellox_remaining_hours": [">", 0],
			"is_group": 0,  # a parent task's hours are its children's
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
