import frappe


def execute():
	"""Re-sync the Vellox Agency workspace so Offers/Services entries land
	on sites installed before [P1-14]."""
	# The workspace moved to the Projects module in [P3-96]; the old path no
	# longer exists, and reload_doc raises on a missing file.
	frappe.reload_doc("vellox_agency_projects", "workspace", "vellox_agency")
