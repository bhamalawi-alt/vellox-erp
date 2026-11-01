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

MAX_REFERENCE_DEPTH = 10

# Reports on records a job may see that still show billing, cost, salary or
# profit amounts ([P4-31]): Finance and the Agency Manager only.
MONEY_REPORTS = frozenset(
	{"Project Billing Summary", "Employee Billing Summary", "Project Profitability", "Project wise Stock Tracking"}
)


def report_doctype(report_name: str) -> str | None:
	"""The record type a report shows; a Custom Report shows its original report's.

	Follows the whole chain of Custom Reports, as Frappe's get_reference_report does.
	"""
	name = report_name
	for _depth in range(MAX_REFERENCE_DEPTH):
		report = frappe.db.get_value("Report", name, ["ref_doctype", "report_type", "reference_report"], as_dict=True)
		if not report:
			return None
		if report.report_type != "Custom Report" or not report.reference_report:
			return report.ref_doctype
		name = report.reference_report
	return None


def can_run_report(report_name: str, user: str | None = None) -> bool:
	user = user or frappe.session.user
	if not security._job_roles(user):
		return True
	doctype = report_doctype(report_name)
	if not doctype:
		return False  # unknown, or a reference chain that does not end
	if security.access_level(doctype, user) in (security.NONE, security.LINK):
		return False
	if report_name in MONEY_REPORTS:
		from vellox_agency.rates import sees_rates

		if not sees_rates(user):
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


@frappe.whitelist()
def make_prepared_report(report_name: str, **kwargs):
	"""Background ("prepared") report runs follow the same rule as direct runs."""
	from frappe.core.doctype.prepared_report import prepared_report

	require_report_access(report_name)
	return _original(prepared_report.make_prepared_report, report_name=report_name, **kwargs)
