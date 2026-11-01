"""Margin-aware estimate panel on Quotation (design section 4, [P3-143]).

Sales enters roles and hours. Each role's cost rate is the default rate Finance
sets on its Activity Type (owner, 2026-11-01); a rate typed into the estimate
is ignored.

labour cost       = sum(hours x the role's rate), company currency
estimated margin  = (base net total - labour cost - vendor cost) / base net total

Who sees what (owner, 2026-11-01):
- The exact margin and the labour cost are for Finance and the Agency Manager
  (Quotation level 3): with the exact margin, anyone who edits hours could work
  out each role's rate. Sales and Operations see the margin band and the
  approval tier.
- A role with no rate does not stop Sales saving a draft: the band shows
  "Unknown", the role is named, and approving or submitting waits until Finance
  sets the rate.

The estimate rows keep roles and hours only. Never modifies ERPNext financial
fields.
"""

import json
import math

import frappe
from frappe import _
from frappe.utils import flt

# Above the estimate panel's level 2 ([P4-34]), which Sales and Operations read.
LABOUR_COST_PERMLEVEL = 3
LABOUR_COST_READERS = ("Vellox Finance", "Agency Manager", "System Manager")
UNKNOWN_BAND = "Unknown: cost rate missing"
LABOUR_COST_FIELDS = [
	{
		"fieldname": "custom_vellox_margin_band",
		"label": "Margin Band",
		"fieldtype": "Data",
		"read_only": 1,
		"no_copy": 1,
		"print_hide": 1,
		"permlevel": 2,
		"insert_after": "custom_vellox_estimated_margin",
	},
	{
		"fieldname": "custom_vellox_missing_rates",
		"label": "Roles Without a Cost Rate",
		"fieldtype": "Small Text",
		"read_only": 1,
		"no_copy": 1,
		"print_hide": 1,
		"permlevel": 2,
		"insert_after": "custom_vellox_margin_band",
		"depends_on": "eval:doc.custom_vellox_missing_rates",
		"description": "Finance sets these on the Activity Type of the same name before the quote can be approved.",
	},
	{
		"fieldname": "custom_vellox_estimated_labour_cost",
		"label": "Estimated Labour Cost (company currency)",
		"fieldtype": "Currency",
		"read_only": 1,
		"no_copy": 1,
		"print_hide": 1,
		"permlevel": LABOUR_COST_PERMLEVEL,
		"insert_after": "custom_vellox_missing_rates",
		"description": "Hours x Finance's role rates when the quote was last saved.",
	},
]


def setup_labour_cost_field() -> None:
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	from vellox_agency.security import grant_permlevel

	create_custom_fields({"Quotation": LABOUR_COST_FIELDS}, update=True)
	for role in LABOUR_COST_READERS:
		grant_permlevel("Quotation", role, LABOUR_COST_PERMLEVEL, "read")
	frappe.clear_cache(doctype="Quotation")


def compute_margin(net_total, estimate_hours_json, vendor_cost) -> frappe._dict:
	"""labour cost, margin % and the roles without a rate, for a company-currency net total.

	With a role missing its rate, labour and margin are None (unknown).
	"""
	rows = _rows(estimate_hours_json)
	vendor = _non_negative(vendor_cost, _("Vendor Cost"))
	rates, missing = _role_rates({row["role"] for row in rows})
	for row in rows:
		row["role"] = rates.get(row["role"].lower(), (row["role"], 0))[0]
	if missing:
		return frappe._dict(rows=rows, labour=None, margin=None, missing=missing)
	labour = flt(sum(row["hours"] * rates[row["role"].lower()][1] for row in rows), 2)
	revenue = flt(net_total)
	margin = flt((revenue - labour - vendor) / revenue * 100, 2) if revenue > 0 else 0.0
	return frappe._dict(rows=rows, labour=labour, margin=margin, missing=[])


def margin_band(margin) -> str:
	"""What Sales and Operations see instead of the exact margin."""
	if margin is None:
		return UNKNOWN_BAND
	if flt(margin) >= 40:
		return _("40% or more")
	if flt(margin) >= 25:
		return _("25% to 40%")
	return _("Under 25%")


def has_estimate(doc) -> bool:
	"""Whether the quote carries a real cost estimate: priced hours or a vendor cost."""
	return flt(doc.get("custom_vellox_estimated_labour_cost")) + flt(doc.get("custom_vellox_vendor_cost")) > 0


def missing_rates(doc) -> list[str]:
	return [role for role in (doc.get("custom_vellox_missing_rates") or "").splitlines() if role]


def apply_estimate_margin(doc, method=None) -> None:
	if doc.doctype != "Quotation":
		return
	result = compute_margin(
		doc.base_net_total, doc.custom_vellox_estimate_hours, doc.custom_vellox_vendor_cost
	)
	if doc.flags.vellox_approving:
		_refuse_changed_rates(doc, result)
	# Keep roles and hours only: the panel must not carry rates (Finance's or typed).
	doc.custom_vellox_estimate_hours = json.dumps(result.rows) if result.rows else None
	doc.custom_vellox_estimated_labour_cost = flt(result.labour)
	doc.custom_vellox_estimated_margin = flt(result.margin)
	doc.custom_vellox_margin_band = margin_band(result.margin)
	doc.custom_vellox_missing_rates = "\n".join(result.missing) or None
	if result.missing:
		frappe.msgprint(
			_(
				"No cost rate is set yet for {0}. The quote is saved, but it cannot be approved until Finance sets it."
			).format(", ".join(frappe.bold(role) for role in result.missing)),
			title=_("Cost rate missing"),
			indicator="orange",
		)


def _refuse_changed_rates(doc, result) -> None:
	"""Approving re-saves the quote; if Finance changed a rate since, the margin moved."""
	before = doc.get_doc_before_save()
	if before and (result.missing or flt(result.margin) != flt(before.custom_vellox_estimated_margin)):
		frappe.throw(
			_(
				"Cost rates changed since this quotation was last saved. Save it again and review the new margin before approving."
			),
			frappe.ValidationError,
			title=_("Cost rates changed"),
		)


def _rows(raw) -> list[dict]:
	rows = []
	for row in _parse_hours(raw):
		role = row.get("role")
		if not isinstance(role, str) or not role.strip():
			frappe.throw(_("Each estimate row needs a role and hours."), frappe.ValidationError)
		rows.append({"role": role.strip(), "hours": _non_negative(row.get("hours"), _("Hours"))})
	return rows


def _non_negative(value, label: str) -> float:
	number = flt(value)
	if not math.isfinite(number):
		frappe.throw(_("{0} must be a number.").format(label), frappe.ValidationError)
	if number < 0:
		frappe.throw(_("{0} cannot be negative.").format(label), frappe.ValidationError)
	return number


def _role_rates(roles: set[str]) -> tuple[dict[str, tuple[str, float]], list[str]]:
	"""{lower-case role: (Activity Type name, rate)} and the roles with no rate, matched in any letter case."""
	if not roles:
		return {}, []
	found = {
		name.lower(): (name, flt(rate))
		for name, rate in frappe.get_all(
			"Activity Type",
			filters={"name": ["in", list(roles)]},
			fields=["name", "costing_rate"],
			as_list=True,
		)
	}
	missing = sorted({role for role in roles if found.get(role.lower(), ("", 0))[1] <= 0})
	return found, missing


def _parse_hours(raw):
	if not raw:
		return []
	if isinstance(raw, str):
		try:
			raw = json.loads(raw, parse_constant=_refuse_constant)
		except ValueError:
			frappe.throw(_("Estimate Hours must be valid JSON."), frappe.ValidationError)
	if not isinstance(raw, list):
		frappe.throw(_("Estimate Hours must be a list of rows."), frappe.ValidationError)
	for row in raw:
		if not isinstance(row, dict) or "hours" not in row:
			frappe.throw(_("Each estimate row needs a role and hours."), frappe.ValidationError)
	return raw


def _refuse_constant(name):
	raise ValueError(name)  # NaN and Infinity are not numbers of hours


def report_missing_role_rates() -> None:
	"""after_migrate: say which delivery roles Finance has not priced yet ([P3-143])."""
	from vellox_agency.setup.roles_rates import delivery_roles

	unpriced = [
		name
		for name, rate in frappe.get_all(
			"Activity Type",
			filters={"name": ["in", delivery_roles()]},
			fields=["name", "costing_rate"],
			as_list=True,
		)
		if flt(rate) <= 0
	]
	if unpriced:
		print(
			"Vellox: these roles have no cost rate, so quotes using them cannot be approved yet. "
			f"Finance sets the rate on the Activity Type: {', '.join(sorted(unpriced))}"
		)
