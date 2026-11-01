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
# Reports that narrow their own rows to the team member running them ([P4-32]).
SELF_SCOPED_REPORTS = frozenset({"Vellox Team Capacity"})

MONEY_REPORTS = frozenset(
	{
		"Project Billing Summary",
		"Employee Billing Summary",
		"Project Profitability",
		"Project wise Stock Tracking",
	}
)


def original_report(report_name: str) -> frappe._dict | None:
	"""The report a (chain of) Custom Report(s) is based on, as Frappe's get_reference_report finds it."""
	name = report_name
	for _depth in range(MAX_REFERENCE_DEPTH):
		report = frappe.db.get_value(
			"Report", name, ["name", "ref_doctype", "report_type", "reference_report"], as_dict=True
		)
		if not report:
			return None
		if report.report_type != "Custom Report" or not report.reference_report:
			return report
		name = report.reference_report
	return None


def report_doctype(report_name: str) -> str | None:
	"""The record type a report shows; a Custom Report shows its original report's."""
	report = original_report(report_name)
	return report.ref_doctype if report else None


def can_run_report(report_name: str, user: str | None = None) -> bool:
	user = user or frappe.session.user
	if not security._job_roles(user):
		return True
	doctype = report_doctype(report_name)
	if not doctype:
		return False  # unknown, or a reference chain that does not end
	if security.access_level(doctype, user) in (security.NONE, security.LINK):
		return False
	if original_report(report_name).name in MONEY_REPORTS:  # a renamed copy too
		from vellox_agency.rates import sees_rates

		if not sees_rates(user):
			return False
	if original_report(report_name).name in SELF_SCOPED_REPORTS:
		return True
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


def _require_readable_columns(report_name: str | None, custom_columns=None) -> None:
	"""Custom columns, sent now or saved on a Custom Report, may not compute hidden fields ([P4-34])."""
	from vellox_agency.api_guard import refuse_hidden_report_columns

	refuse_hidden_report_columns(custom_columns)
	if report_name and frappe.db.get_value("Report", report_name, "report_type") == "Custom Report":
		refuse_hidden_report_columns(query_report.get_report_doc(report_name).get("custom_columns"))


@frappe.whitelist()
@frappe.read_only()
def run(report_name: str, **kwargs):
	require_report_access(report_name)
	_require_readable_columns(report_name, kwargs.get("custom_columns"))
	return _original(query_report.run, report_name=report_name, **kwargs)


@frappe.whitelist()
def save_report(reference_report: str, report_name: str, columns: str, filters: str):
	"""Saving a Custom Report keeps its columns for later runs."""
	require_report_access(reference_report)
	_require_readable_columns(None, columns)
	return _original(
		query_report.save_report,
		reference_report=reference_report,
		report_name=report_name,
		columns=columns,
		filters=filters,
	)


@frappe.whitelist()
def get_script(report_name: str):
	require_report_access(report_name)
	return _original(query_report.get_script, report_name=report_name)


@frappe.whitelist()
def make_prepared_report(report_name: str, **kwargs):
	"""Background ("prepared") report runs follow the same rule as direct runs."""
	from frappe.core.doctype.prepared_report import prepared_report

	require_report_access(report_name)
	_require_readable_columns(report_name, kwargs.get("custom_columns"))
	return _original(prepared_report.make_prepared_report, report_name=report_name, **kwargs)
