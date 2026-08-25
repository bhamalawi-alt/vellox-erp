"""Margin-aware estimate panel on Quotation (design section 4).

Computes estimated margin percent from standard net_total minus planned
labor cost (role/hours/rate JSON) and vendor cost. Never modifies ERPNext
financial fields.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt


def compute_margin(net_total, estimate_hours_json, vendor_cost) -> float:
	labor_cost = 0.0
	for row in _parse_hours(estimate_hours_json):
		hours = flt(row.get("hours"))
		rate = flt(row.get("rate"))
		labor_cost += hours * rate
	vendor = flt(vendor_cost)
	revenue = flt(net_total)
	if revenue <= 0:
		return 0.0
	return round((revenue - labor_cost - vendor) / revenue * 100, 2)


def apply_estimate_margin(doc, method=None) -> None:
	if doc.doctype != "Quotation":
		return
	doc.custom_vellox_estimated_margin = compute_margin(
		doc.net_total, doc.custom_vellox_estimate_hours, doc.custom_vellox_vendor_cost
	)


def _parse_hours(raw):
	if not raw:
		return []
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except ValueError:
			frappe.throw(_("Estimate Hours must be valid JSON."), frappe.ValidationError)
	for row in raw:
		if not isinstance(row, dict) or "hours" not in row:
			frappe.throw(_("Each estimate row needs role, hours and rate."), frappe.ValidationError)
	return raw
