"""Built-in reports follow job access ([P3-147], owner decision 2026-11-01).

A job may run a script or query report only when its access lets it see the
report's main record type. Team members and staff get no project, task or
timesheet reports for now: those reports are not narrowed to their projects.
"""

from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase


@contextmanager
def _as_job(*jobs):
	with patch("vellox_agency.security._job_roles", return_value=set(jobs)):
		yield


ROUTES = {
	"frappe.desk.query_report.run": "vellox_agency.report_guard.run",
	"frappe.desk.query_report.get_script": "vellox_agency.report_guard.get_script",
	"frappe.core.doctype.prepared_report.prepared_report.make_prepared_report": "vellox_agency.report_guard.make_prepared_report",
}


class TestWhoRunsWhichReport(FrappeTestCase):
	def _can(self, report, *jobs):
		from vellox_agency.report_guard import can_run_report

		with _as_job(*jobs):
			return can_run_report(report, "someone@example.com")

	def test_reports_follow_the_jobs_record_access(self):
		cases = [
			("Lead Details", ("Vellox Sales",), True),
			("Lead Details", ("Vellox Project Manager",), False),
			("Lead Details", ("Vellox Finance",), False),
			("Sales Order Analysis", ("Vellox Sales",), False),
			("Accounts Receivable", ("Vellox Finance",), True),
			("Accounts Receivable", ("Vellox Sales",), False),
			("Project Summary", ("Vellox Project Manager",), True),
			("Delayed Tasks Summary", ("Vellox Finance",), False),
		]
		for report, jobs, expected in cases:
			with self.subTest(report=report, jobs=jobs):
				self.assertEqual(self._can(report, *jobs), expected)

	def test_team_members_and_staff_get_no_project_task_or_timesheet_reports(self):
		for job in ("Vellox Team Member", "Agency Staff"):
			for report in ("Project Summary", "Delayed Tasks Summary", "Daily Timesheet Summary"):
				with self.subTest(job=job, report=report):
					self.assertFalse(self._can(report, job))

	def test_a_second_job_that_sees_the_records_allows_the_report(self):
		self.assertTrue(self._can("Lead Details", "Vellox Project Manager", "Vellox Sales"))
		# A team member who is also a Project Manager is not team-scoped.
		self.assertTrue(self._can("Project Summary", "Vellox Team Member", "Vellox Project Manager"))

	def test_the_agency_manager_and_users_without_a_job_keep_every_report(self):
		for report in ("Lead Details", "Accounts Receivable", "Project Summary"):
			with self.subTest(report=report):
				self.assertTrue(self._can(report, "Agency Manager"))
				self.assertTrue(self._can(report))

	def test_an_unknown_report_is_refused_for_job_users(self):
		self.assertFalse(self._can("No Such Report", "Vellox Sales"))

	def test_a_custom_report_of_a_custom_report_follows_the_original(self):
		from vellox_agency.report_guard import report_doctype

		def custom(base):
			doc = frappe.get_doc(
				{
					"doctype": "Report",
					"report_name": f"_Test Custom {frappe.generate_hash(length=6)}",
					"report_type": "Custom Report",
					"reference_report": base,
					"ref_doctype": "Lead",
					"module": "Vellox Agency",
					"is_standard": "No",
					"json": "{}",
				}
			).insert(ignore_permissions=True)
			frappe.db.set_value("Report", doc.name, "ref_doctype", "Note", update_modified=False)
			return doc.name

		self.assertEqual(report_doctype(custom(custom("Lead Details"))), "Lead")

	def test_a_custom_report_follows_the_report_it_is_based_on(self):
		from vellox_agency.report_guard import report_doctype

		custom = frappe.get_doc(
			{
				"doctype": "Report",
				"report_name": f"_Test Custom Lead {frappe.generate_hash(length=6)}",
				"report_type": "Custom Report",
				"reference_report": "Lead Details",
				"ref_doctype": "Lead",
				"module": "Vellox Agency",
				"is_standard": "No",
				"json": "{}",
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Report", custom.name, "ref_doctype", "Note", update_modified=False)
		self.assertEqual(report_doctype(custom.name), "Lead")


class TestReportRoutes(FrappeTestCase):
	def test_running_and_loading_reports_are_guarded(self):
		overrides = frappe.get_hooks("override_whitelisted_methods")
		for original, guard in ROUTES.items():
			with self.subTest(route=original):
				self.assertEqual(overrides.get(original), [guard])

	def test_a_refused_report_reads_nothing(self):
		from vellox_agency import report_guard

		for name, kwargs in (("run", {"report_name": "Lead Details"}), ("get_script", {"report_name": "Lead Details"})):
			with self.subTest(route=name), _as_job("Vellox Finance"):
				with patch.object(report_guard, "_original", side_effect=AssertionError("data read")):
					with self.assertRaisesRegex(frappe.PermissionError, "Lead Details"):
						getattr(report_guard, name)(**kwargs)

	def test_a_refused_report_cannot_be_queued_to_run_in_the_background(self):
		from vellox_agency import report_guard

		with _as_job("Vellox Finance"), patch.object(report_guard, "_original", side_effect=AssertionError("queued")):
			with self.assertRaisesRegex(frappe.PermissionError, "Lead Details"):
				report_guard.make_prepared_report(report_name="Lead Details", filters="{}")

	def test_an_allowed_report_runs_as_before(self):
		from vellox_agency import report_guard

		with _as_job("Vellox Finance"), patch.object(report_guard, "_original", return_value={"result": []}) as original:
			self.assertEqual(report_guard.run(report_name="Accounts Receivable", filters="{}"), {"result": []})
			original.assert_called_once()

	def test_exporting_a_report_follows_the_same_rule(self):
		# Finance may export lists, but not a report on records its job cannot see.
		from vellox_agency import export_guard

		with _as_job("Vellox Finance"), patch.object(export_guard, "_original", side_effect=AssertionError("data read")):
			frappe.local.form_dict = frappe._dict(report_name="Lead Details")
			with self.assertRaisesRegex(frappe.PermissionError, "Lead Details"):
				export_guard.export_report()


class TestRealFinanceProfile(FrappeTestCase):
	def test_finance_cannot_run_lead_details_through_the_request_handler(self):
		from types import SimpleNamespace

		from frappe.handler import execute_cmd

		from vellox_agency.security import JOB_PROFILES

		user = "ra-finance@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc({"doctype": "User", "email": user, "first_name": "RA", "send_welcome_email": 0}).insert(
				ignore_permissions=True
			)
			frappe.get_doc("User", user).add_roles(*JOB_PROFILES["Finance"])
		previous = getattr(frappe.local, "request", None)
		frappe.local.request = SimpleNamespace(method="POST", headers={})
		try:
			with self.set_user(user):
				frappe.local.form_dict = frappe._dict(report_name="Lead Details", filters="{}", cmd="x")
				with self.assertRaisesRegex(frappe.PermissionError, "Lead Details"):
					execute_cmd("frappe.desk.query_report.run")
		finally:
			frappe.local.request = previous
