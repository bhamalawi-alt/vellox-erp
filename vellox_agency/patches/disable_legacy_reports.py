import frappe

from vellox_agency.deprecations import LEGACY_REPORTS


def execute():
	"""Disable the script reports built on the deprecated ledgers [P3-96].

	The report files carry disabled = 1 for new installs, but Frappe's file
	sync never overwrites a Report's "disabled" flag on an existing site.
	"""
	for report in LEGACY_REPORTS:
		if frappe.db.exists("Report", report):
			frappe.db.set_value("Report", report, "disabled", 1)
