import frappe


def execute():
	"""Re-sync the Vellox Agency workspace so Offers/Services entries land
	on sites installed before [P1-14]."""
	frappe.reload_doc("vellox_agency_reports", "workspace", "vellox_agency")
