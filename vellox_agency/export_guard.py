"""Exporting lists is for the Agency Manager and Finance (owner, 2026-11-01, [P3-141]).

Frappe decides export rights from role permissions alone, and a role such as
Sales User is shared by the Sales and Finance jobs, so the rule cannot live in
role permissions. Instead every route that downloads records is wrapped here
(hooks.override_whitelisted_methods). Users without a Vellox job (Administrator,
System Managers) keep ERPNext's own export rights. Viewing, printing and
emailing single records are unchanged.
"""

import frappe
from frappe import _
from frappe.core.doctype.data_export import exporter
from frappe.core.doctype.data_import import data_import
from frappe.desk import query_report, reportview

from vellox_agency import security

EXPORT_ROLES = frozenset({"Agency Manager", "Vellox Finance"})


def can_export_lists(user: str | None = None) -> bool:
	jobs = security._job_roles(user or frappe.session.user)
	return not jobs or bool(jobs & EXPORT_ROLES)


def _require_export() -> None:
	if not can_export_lists():
		frappe.throw(_("Only Finance and the Agency Manager can export lists."), frappe.PermissionError)


def _original(fn, **kwargs):
	# frappe.call drops request keys (cmd, ...) the original does not accept.
	return frappe.call(fn, **kwargs)


@frappe.whitelist()
@frappe.read_only()
def export_query():
	"""Report Builder and list view export."""
	_require_export()
	return _original(reportview.export_query)


@frappe.whitelist()
def export_report():
	"""Query and script report export."""
	_require_export()
	return _original(query_report.export_query)


@frappe.whitelist()
def export_data(**kwargs):
	"""The Data Export tool."""
	_require_export()
	return _original(exporter.export_data, **kwargs)


@frappe.whitelist()
def download_template(doctype: str, export_records: str | None = None, **kwargs):
	"""Data Import templates: a blank template holds no records, so anyone may get one."""
	if export_records != "blank_template":
		_require_export()
	return _original(data_import.download_template, doctype=doctype, export_records=export_records, **kwargs)
