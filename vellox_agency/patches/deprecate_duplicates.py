import frappe
from vellox_agency.deprecations import audit_record_counts


def execute():
	frappe.logger("vellox_deprecation_audit", allow_site=True).info(
		"patch deprecate_duplicates: recording baseline ledger counts"
	)
	audit_record_counts()
