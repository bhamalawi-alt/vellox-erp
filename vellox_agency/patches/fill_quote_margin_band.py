"""Give quotes saved before [P3-143] a margin band.

Sales and Operations now see the band instead of the exact margin, so older
quotes would otherwise show them nothing until their next save.
"""

import frappe


def execute():
	from vellox_agency.estimate import margin_band

	if not frappe.get_meta("Quotation").has_field("custom_vellox_margin_band"):
		from vellox_agency.estimate import setup_labour_cost_field

		setup_labour_cost_field()
	for name, margin in frappe.get_all(
		"Quotation",
		filters={"custom_vellox_margin_band": ["is", "not set"]},
		fields=["name", "custom_vellox_estimated_margin"],
		as_list=True,
	):
		frappe.db.set_value(
			"Quotation", name, "custom_vellox_margin_band", margin_band(margin), update_modified=False
		)
