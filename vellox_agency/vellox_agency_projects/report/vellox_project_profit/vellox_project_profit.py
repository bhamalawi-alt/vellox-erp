"""Budget used, forecast and profit per project (capacity plan sections 5 to 7, [P4-33]).

Finance and the Agency Manager see the amounts. Project Managers see budget
used %, margin drift and the colour for their own projects, Operations for
all projects, with no amounts. Team members and Sales cannot run it.
"""

import frappe
from frappe import _

from vellox_agency import security
from vellox_agency.profit import REPORTING_CURRENCY, projects_profit
from vellox_agency.rates import sees_rates

AMOUNTS = ("contract_value", "budget", "cost_to_date", "remaining_cost", "forecast_cost", "expected_margin")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	user = frappe.session.user
	if security.access_level("Project", user) in (security.NONE, security.LINK) or security._team_scoped(
		user
	):
		frappe.throw(_("Your job does not give access to project profit."), frappe.PermissionError)
	with_amounts = sees_rates(user)

	project_filters = {"custom_vellox_quotation": ["is", "set"]}
	if filters.status:
		project_filters["status"] = filters.status
	if filters.project:
		project_filters["name"] = filters.project
	if not with_amounts and _own_projects_only(user):
		project_filters["custom_vellox_project_manager"] = user
	projects = frappe.get_list(
		"Project",
		filters=project_filters,
		fields=["name", "project_name", "custom_vellox_project_manager"],
		order_by="name",
	)
	figures, errors = projects_profit([p.name for p in projects])

	rows = []
	for project in projects:
		row = {
			"project": project.name,
			"project_name": project.project_name,
			"project_manager": project.custom_vellox_project_manager,
		}
		if project.name in errors:
			row["note"] = errors[project.name]
		else:
			p = figures[project.name]
			row.update(budget_used=p.budget_used, margin_drift=p.margin_drift, signal=p.signal)
			if p.unpriced_hours:
				row["note"] = _("{0} remaining hours have no cost rate").format(p.unpriced_hours)
			if with_amounts:
				row.update({field: p[field] for field in AMOUNTS}, currency=REPORTING_CURRENCY)
		rows.append(row)
	return _columns(with_amounts), rows


def _own_projects_only(user: str) -> bool:
	"""Project Managers see their own projects; Operations sees all (section 7)."""
	return "Vellox Operations" not in security._job_roles(user)


def _columns(with_amounts: bool) -> list[dict]:
	columns = [
		{
			"fieldname": "project",
			"label": _("Project"),
			"fieldtype": "Link",
			"options": "Project",
			"width": 120,
		},
		{"fieldname": "project_name", "label": _("Name"), "fieldtype": "Data", "width": 200},
		{
			"fieldname": "project_manager",
			"label": _("Project Manager"),
			"fieldtype": "Link",
			"options": "User",
			"width": 160,
		},
		{"fieldname": "signal", "label": _("Signal"), "fieldtype": "Data", "width": 90},
		{"fieldname": "budget_used", "label": _("Budget Used %"), "fieldtype": "Percent", "width": 110},
		{
			"fieldname": "margin_drift",
			"label": _("Margin Drift (pts)"),
			"fieldtype": "Float",
			"precision": 1,
			"width": 120,
		},
	]
	if with_amounts:
		money = {"fieldtype": "Currency", "options": "currency", "width": 120}
		columns += [
			{"fieldname": "contract_value", "label": _("Contract (USD)"), **money},
			{"fieldname": "budget", "label": _("Budget (USD)"), **money},
			{"fieldname": "cost_to_date", "label": _("Actual Cost (USD)"), **money},
			{"fieldname": "remaining_cost", "label": _("Remaining (USD)"), **money},
			{"fieldname": "forecast_cost", "label": _("Forecast Cost (USD)"), **money},
			{
				"fieldname": "expected_margin",
				"label": _("Expected Margin %"),
				"fieldtype": "Percent",
				"width": 120,
			},
		]
	columns.append({"fieldname": "note", "label": _("Note"), "fieldtype": "Data", "width": 260})
	return columns
