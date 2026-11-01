"""Margin-aware estimate panel on Quotation (design section 4, [P3-143]).

Sales enters roles and hours. Each role's cost rate is the default rate Finance
sets on its Activity Type (owner, 2026-11-01); a rate typed into the estimate
is ignored, and a role with no rate blocks the margin until Finance sets one.

labour cost       = sum(hours x the role's rate), company currency
estimated margin  = (base net total - labour cost - vendor cost) / base net total

The labour cost is stored on the quote where only Finance and the Agency
Manager read it; the estimate rows keep roles and hours only, so the panel
(read by Sales and Operations) never shows Finance's rates. Never modifies
ERPNext financial fields.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt

# Above the estimate panel's level 2 ([P4-34]), which Sales and Operations read.
LABOUR_COST_PERMLEVEL = 3
LABOUR_COST_READERS = ("Vellox Finance", "Agency Manager", "System Manager")
LABOUR_COST_FIELD = {
	"fieldname": "custom_vellox_estimated_labour_cost",
	"label": "Estimated Labour Cost (company currency)",
	"fieldtype": "Currency",
	"read_only": 1,
	"no_copy": 1,
	"print_hide": 1,
	"permlevel": LABOUR_COST_PERMLEVEL,
	"insert_after": "custom_vellox_estimated_margin",
	"description": "Hours x Finance's role rates when the quote was last saved.",
}


def setup_labour_cost_field() -> None:
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	from vellox_agency.security import grant_permlevel

	create_custom_fields({"Quotation": [LABOUR_COST_FIELD]}, update=True)
	for role in LABOUR_COST_READERS:
		grant_permlevel("Quotation", role, LABOUR_COST_PERMLEVEL, "read")
	frappe.clear_cache(doctype="Quotation")


def compute_margin(net_total, estimate_hours_json, vendor_cost) -> tuple[float, float]:
	"""(labour cost, margin %) for a company-currency net total."""
	rows = _rows(estimate_hours_json)
	rates = _role_rates({row["role"] for row in rows})
	labour = sum(flt(row["hours"]) * rates[row["role"]] for row in rows)
	revenue = flt(net_total)
	if revenue <= 0:
		return round(labour, 2), 0.0
	return round(labour, 2), round((revenue - labour - flt(vendor_cost)) / revenue * 100, 2)


def has_estimate(doc) -> bool:
	"""Whether the quote carries any cost estimate (hours or vendor cost)."""
	try:
		rows = _parse_hours(doc.get("custom_vellox_estimate_hours"))
	except frappe.ValidationError:
		return False
	return bool(rows) or flt(doc.get("custom_vellox_vendor_cost")) > 0


def apply_estimate_margin(doc, method=None) -> None:
	if doc.doctype != "Quotation":
		return
	rows = _rows(doc.custom_vellox_estimate_hours)
	# Keep roles and hours only: the panel must not carry rates (Finance's or typed).
	doc.custom_vellox_estimate_hours = json.dumps(rows) if rows else None
	labour, margin = compute_margin(
		doc.base_net_total, doc.custom_vellox_estimate_hours, doc.custom_vellox_vendor_cost
	)
	doc.custom_vellox_estimated_labour_cost = labour
	doc.custom_vellox_estimated_margin = margin


def _rows(raw) -> list[dict]:
	rows = []
	for row in _parse_hours(raw):
		role = row.get("role")
		if not isinstance(role, str) or not role.strip():
			frappe.throw(_("Each estimate row needs a role and hours."), frappe.ValidationError)
		rows.append({"role": role.strip(), "hours": flt(row.get("hours"))})
	return rows


def _role_rates(roles: set[str]) -> dict[str, float]:
	"""Finance's default cost rate per role; a missing or zero rate blocks the margin."""
	if not roles:
		return {}
	rates = dict(
		frappe.get_all(
			"Activity Type",
			filters={"name": ["in", list(roles)]},
			fields=["name", "costing_rate"],
			as_list=True,
		)
	)
	missing = sorted(role for role in roles if flt(rates.get(role)) <= 0)
	if missing:
		frappe.throw(
			_("No cost rate is set for {0}. Finance sets it on the Activity Type of the same name.").format(
				", ".join(frappe.bold(role) for role in missing)
			),
			frappe.ValidationError,
			title=_("Cost rate missing"),
		)
	return {role: flt(rate) for role, rate in rates.items()}


def _parse_hours(raw):
	if not raw:
		return []
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except ValueError:
			frappe.throw(_("Estimate Hours must be valid JSON."), frappe.ValidationError)
	if not isinstance(raw, list):
		frappe.throw(_("Estimate Hours must be a list of rows."), frappe.ValidationError)
	for row in raw:
		if not isinstance(row, dict) or "hours" not in row:
			frappe.throw(_("Each estimate row needs a role and hours."), frappe.ValidationError)
	return raw
