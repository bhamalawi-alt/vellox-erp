"""Deprecation of duplicate custom business ledgers.

ERPNext remains authoritative for Customer/Contact/Address, Project,
Timesheet, Expense Claim/Purchase Invoice and Sales Invoice (see
docs/migrations/deprecation-map.md). New records in the parallel custom
ledgers are blocked; existing rows stay readable until retention approval.
"""

import frappe
from frappe import _
from frappe.exceptions import ValidationError

DEPRECATION_TARGETS = {
	"Client Account": "Customer / Contact / Address",
	"Agency Project": "Project",
	"Agency Timesheet": "Timesheet",
	"Expense": "Expense Claim or Purchase Invoice",
	"Agency Invoice": "Sales Invoice",
	"Engagement": "Quotation + Subscription (approved ERPNext-backed model)",
	"Retainer": "Subscription (approved ERPNext-backed model)",
}

_EXEMPT_FLAGS = ("in_install", "in_migrate", "in_patch", "in_test", "in_uninstall")


def _exempt() -> bool:
	return any(frappe.flags.get(flag) for flag in _EXEMPT_FLAGS)


def guard_deprecated_doctype(doc, method=None) -> None:
	if _exempt():
		return
	doctype = doc.doctype
	if doctype not in DEPRECATION_TARGETS:
		return
	target = DEPRECATION_TARGETS[doctype]
	frappe.throw(
		_("{0} is deprecated. Use {1} instead.").format(
			frappe.bold(doctype), frappe.bold(target)
		),
		ValidationError,
		title=_("Deprecated record"),
	)


def audit_record_counts() -> dict[str, int]:
	"""Log per-ledger record counts; safe to run any number of times."""
	counts = {
		doctype: frappe.db.count(doctype) for doctype in DEPRECATION_TARGETS
	}
	logger = frappe.logger("vellox_deprecation_audit", allow_site=True)
	for doctype, count in counts.items():
		logger.info(f"[DEPRECATION AUDIT] {doctype}: {count} record(s)")

	# Durable, desk-visible audit trail (one row per audit run).
	import json

	frappe.log_error(
		title="Vellox Deprecation Audit",
		message=json.dumps(counts, indent=2),
	)
	return counts


def execute() -> str:
	"""Patch entry point: idempotent deprecation audit.

	Data migration to ERPNext targets is a no-op until real data exists;
	the measured counts are recorded as the audit trail for this release.
	"""
	counts = audit_record_counts()
	total = sum(counts.values())
	return f"Audited {len(counts)} deprecated ledgers holding {total} record(s)."
