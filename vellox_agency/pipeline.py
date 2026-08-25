"""Pipeline behaviors: stage-driven probability and lost-reason enforcement."""

import frappe
from frappe import _


def apply_stage_probability(doc, method=None) -> None:
	if doc.doctype != "Opportunity" or not doc.sales_stage:
		return
	prob = frappe.db.get_value("Sales Stage", doc.sales_stage, "custom_vellox_probability")
	if prob is not None:
		doc.custom_vellox_probability = prob


def require_lost_reason(doc, method=None) -> None:
	if doc.doctype == "Opportunity" and doc.status == "Lost":
		if not doc.get("lost_reasons"):
			frappe.throw(
				_("A lost Opportunity requires at least one lost reason."),
				frappe.ValidationError,
			)


def require_lost_reason(doc, method=None) -> None:
	if doc.doctype == "Opportunity" and doc.status == "Lost":
		if not doc.get("lost_reasons"):
			frappe.throw(
				_("A lost Opportunity requires at least one lost reason."),
				frappe.ValidationError,
			)


def _allowed_customers(user: str | None) -> list[str]:
	"""Customer names explicitly permitted via User Permission (may be empty
	meaning unrestricted — mirrors standard ERPNext semantics)."""
	return frappe.get_all(
		"User Permission",
		filters={"user": user or frappe.session.user, "allow": "Customer"},
		pluck="for_value",
	)


def weighted_pipeline(user=None) -> list[dict]:
	"""Permission-aware weighted demand grouped by company + currency.

	Uses frappe.get_list(user=...) so User Permissions and role filters are
	enforced by the framework, never bypassed.
	"""
	from frappe.utils import flt

	user = user or frappe.session.user
	filters = {"status": ("not in", ["Lost", "Closed"])}
	allowed = _allowed_customers(user)
	if allowed:
		# party_name is a Dynamic Link; standard User Permissions do not
		# filter it (see [P6-40]) — scope explicitly here.
		filters["party_name"] = ("in", allowed)
	rows = frappe.get_list(
		"Opportunity",
		filters=filters,
		fields=["company", "currency", "opportunity_amount", "custom_vellox_probability"],
		user=user,
	)

	aggregate: dict[tuple, float] = {}
	for row in rows:
		key = (row.company or "", row.currency or "")
		probability = flt(row.custom_vellox_probability)
		aggregate[key] = aggregate.get(key, 0.0) + flt(row.opportunity_amount) * probability / 100.0

	return [
		{"company": company, "currency": currency, "weighted_total": total}
		for (company, currency), total in sorted(aggregate.items())
	]


def get_stale_opportunities(days: int = 14, user=None) -> list[dict]:
	"""Open opportunities untouched for N days — feeds stale reminders."""
	from frappe.utils import add_to_date, now_datetime

	cutoff = add_to_date(now_datetime(), days=-days)
	return frappe.get_list(
		"Opportunity",
		filters={
			"modified": ("<", cutoff),
			"status": ("not in", ["Lost", "Closed", "Converted"]),
		},
		fields=["name", "party_name", "sales_stage", "custom_vellox_probability", "modified"],
		order_by="modified asc",
		user=user,
	)
