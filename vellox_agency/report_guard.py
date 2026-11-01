"""Built-in reports follow job access (owner, 2026-11-01, [P3-147]).

Script and query reports build their own SQL, so the job access hooks never
see their rows; Frappe only checks the report's roles and role-level rights on
its main record type (ref_doctype). Running and loading such a report is
therefore gated here (hooks.override_whitelisted_methods), and exporting one in
export_guard. Report Builder reports read through the list API, which already
applies job access.

Team members and staff get no project, task or timesheet reports for now:
those reports list every project, not only theirs.
"""

import frappe
from frappe import _
from frappe.desk import query_report

from vellox_agency import security


def report_doctype(report_name: str) -> str | None:
	"""The record type a report shows; a Custom Report shows its base report's."""
	report = frappe.db.get_value(
		"Report", report_name, ["ref_doctype", "report_type", "reference_report"], as_dict=True
	)
	if not report:
		return None
	if report.report_type == "Custom Report" and report.reference_report:
		return frappe.db.get_value("Report", report.reference_report, "ref_doctype")
	return report.ref_doctype


def can_run_report(report_name: str, user: str | None = None) -> bool:
	user = user or frappe.session.user
	if not security._job_roles(user):
		return True
	doctype = report_doctype(report_name)
	if not doctype:
		return True  # unknown report: Frappe's own lookup refuses it
	if security.access_level(doctype, user) in (security.NONE, security.LINK):
		return False
	return not (security._team_scoped(user) and doctype in security.TEAM_SCOPED_DOCTYPES)


def require_report_access(report_name: str | None) -> None:
	if report_name and not can_run_report(report_name):
		frappe.throw(
			_("Your job does not give access to the report {0}.").format(frappe.bold(report_name)),
			frappe.PermissionError,
		)


def _original(fn, **kwargs):
	# frappe.call drops request keys (cmd, ...) the original does not accept.
	return frappe.call(fn, **kwargs)


@frappe.whitelist()
@frappe.read_only()
def run(report_name: str, **kwargs):
	require_report_access(report_name)
	return _original(query_report.run, report_name=report_name, **kwargs)


@frappe.whitelist()
def get_script(report_name: str):
	require_report_access(report_name)
	return _original(query_report.get_script, report_name=report_name)
