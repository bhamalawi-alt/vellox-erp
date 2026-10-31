import frappe

# Inlined so this patch keeps working after the reports and any shared
# constant are removed ([P7-111]).
LEGACY_REPORTS = (
	"Agency KPI",
	"Agency Utilization",
	"Budget vs Actual",
	"Invoice Register",
	"Production Pipeline",
)


def execute():
	"""Disable the script reports built on the deprecated ledgers [P3-96].

	The report files carry disabled = 1 for new installs, but Frappe's file
	sync never overwrites a Report's "disabled" flag on an existing site.

	The workspace is force-reloaded first: Frappe shows it only to users who
	can read something in its module, and the old "Vellox Agency Reports"
	module holds nothing but these reports. A workspace edited on the site
	after the file's timestamp would otherwise keep that module and vanish.
	"""
	frappe.reload_doc("vellox_agency_projects", "workspace", "vellox_agency", force=True)
	for report in LEGACY_REPORTS:
		if frappe.db.exists("Report", report):
			frappe.db.set_value("Report", report, "disabled", 1)
