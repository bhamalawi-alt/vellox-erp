"""Delivery roles, rate types and keeping money with Finance ([P4-31], plan sections 2 and 7).

Project Managers and Operations see hours and percentages, never amounts or
rates; Finance and the Agency Manager see both.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from vellox_agency.security import JOB_PROFILES

PM = "rr-pm@example.com"
FINANCE = "rr-finance@example.com"
TEAM = "rr-team@example.com"

HIDDEN = {
	"Project": ["total_costing_amount", "total_billed_amount", "gross_margin", "estimated_costing"],
	"Task": ["total_costing_amount", "total_billing_amount"],
	"Timesheet": ["total_costing_amount", "total_billed_amount"],
	"Activity Type": ["costing_rate", "billing_rate"],
}


def _user(email, roles):
	# Real job profiles, but never Sales or Agency Manager (they join lead routing on the test site).
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": "RR", "send_welcome_email": 0}).insert(
			ignore_permissions=True
		)
		frappe.get_doc("User", email).add_roles(*roles)
	return email


class _RatesCase(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.security import setup_roles_and_permissions
		from vellox_agency.setup.roles_rates import setup_delivery_roles
		from vellox_agency.tests.test_offer_builder import _bootstrap_erpnext_test_fixtures

		_bootstrap_erpnext_test_fixtures()
		setup_delivery_roles()
		setup_roles_and_permissions()
		_user(PM, JOB_PROFILES["Project Manager"])
		_user(FINANCE, JOB_PROFILES["Finance"])
		_user(TEAM, JOB_PROFILES["Team Member"])


class TestDeliveryRoles(_RatesCase):
	def test_every_practice_step_role_is_a_designation_and_a_rate_type(self):
		from vellox_agency.setup.practice_templates import PRACTICE_TEMPLATES

		roles = {step[4] for steps in PRACTICE_TEMPLATES.values() for step in steps}
		self.assertIn("Developer", roles)
		for role in roles:
			with self.subTest(role=role):
				self.assertTrue(frappe.db.exists("Designation", role))
				self.assertTrue(frappe.db.exists("Activity Type", role))


class TestMoneyStaysWithFinance(_RatesCase):
	def _readable_levels(self, doctype, user):
		with self.set_user(user):
			return set(frappe.new_doc(doctype).get_permlevel_access("read"))

	def test_money_fields_sit_above_the_level_pms_and_team_members_read(self):
		for doctype, fields in HIDDEN.items():
			meta = frappe.get_meta(doctype)
			for user in (PM, TEAM):
				readable = self._readable_levels(doctype, user)
				for field in fields:
					with self.subTest(doctype=doctype, field=field, user=user):
						self.assertNotIn(meta.get_field(field).permlevel, readable)

	def test_timesheet_row_amounts_are_hidden_too(self):
		meta = frappe.get_meta("Timesheet Detail")
		readable = self._readable_levels("Timesheet", PM)
		for field in ("costing_rate", "costing_amount", "base_costing_rate", "base_costing_amount", "base_billing_amount"):
			with self.subTest(field=field):
				self.assertNotIn(meta.get_field(field).permlevel, readable)

	def test_finance_reads_them(self):
		for doctype, fields in HIDDEN.items():
			meta = frappe.get_meta(doctype)
			readable = self._readable_levels(doctype, FINANCE)
			for field in fields:
				with self.subTest(doctype=doctype, field=field):
					self.assertIn(meta.get_field(field).permlevel, readable)

	def test_per_person_rates_are_for_finance_and_the_agency_manager(self):
		from vellox_agency.security import EDIT, NONE, access_level

		with patch("vellox_agency.security._job_roles", return_value={"Vellox Project Manager"}):
			self.assertEqual(access_level("Activity Cost", PM), NONE)
		with patch("vellox_agency.security._job_roles", return_value={"Vellox Operations"}):
			self.assertEqual(access_level("Activity Cost", PM), NONE)
		with patch("vellox_agency.security._job_roles", return_value={"Vellox Finance"}):
			self.assertEqual(access_level("Activity Cost", FINANCE), EDIT)

	def test_the_timesheet_rate_lookup_returns_no_rate_to_other_jobs(self):
		# The Timesheet form fetches a person's rate through a whitelisted call;
		# the server recomputes cost on save, so other jobs need no number.
		from vellox_agency.rates import get_activity_cost

		activity = frappe.db.get_value("Activity Type", "Developer", "name")
		frappe.db.set_value("Activity Type", activity, {"costing_rate": 30, "billing_rate": 60})
		with self.set_user(PM):
			self.assertEqual(
				{k: get_activity_cost(activity_type=activity).get(k) for k in ("costing_rate", "billing_rate")},
				{"costing_rate": 0, "billing_rate": 0},
			)
		with self.set_user(FINANCE):
			self.assertEqual(get_activity_cost(activity_type=activity).get("costing_rate"), 30)

	def test_the_rate_lookup_is_routed_through_vellox(self):
		self.assertEqual(
			frappe.get_hooks("override_whitelisted_methods").get(
				"erpnext.projects.doctype.timesheet.timesheet.get_activity_cost"
			),
			["vellox_agency.rates.get_activity_cost"],
		)


class TestMoneyRoutes(_RatesCase):
	"""Routes that returned money despite the hidden fields (review of 378ffb3)."""

	def test_timesheet_helpers_that_return_amounts_are_for_finance(self):
		from vellox_agency import rates

		for name in ("get_projectwise_timesheet_data", "get_timesheet_data", "get_timesheet_detail_rate", "make_sales_invoice"):
			with self.subTest(route=name), self.set_user(PM):
				with patch.object(rates, "_original", side_effect=AssertionError("data read")):
					with self.assertRaises(frappe.PermissionError):
						getattr(rates, name)()
		overrides = frappe.get_hooks("override_whitelisted_methods")
		for name in ("get_projectwise_timesheet_data", "get_timesheet_data", "get_timesheet_detail_rate", "make_sales_invoice"):
			with self.subTest(hook=name):
				self.assertEqual(
					overrides.get(f"erpnext.projects.doctype.timesheet.timesheet.{name}"), [f"vellox_agency.rates.{name}"]
				)

	def test_billing_and_profit_reports_are_for_finance(self):
		from vellox_agency.report_guard import can_run_report

		for report in ("Project Billing Summary", "Employee Billing Summary", "Project Profitability", "Project wise Stock Tracking"):
			with self.subTest(report=report):
				self.assertFalse(can_run_report(report, PM))
				self.assertTrue(can_run_report(report, FINANCE))
		self.assertTrue(can_run_report("Project Summary", PM))  # hours and progress only

	def test_a_renamed_copy_of_a_money_report_is_blocked_too(self):
		from vellox_agency.report_guard import can_run_report

		copy = frappe.get_doc(
			{
				"doctype": "Report",
				"report_name": f"_Test PBS Copy {frappe.generate_hash(length=6)}",
				"report_type": "Custom Report",
				"reference_report": "Project Billing Summary",
				"ref_doctype": "Timesheet",
				"module": "Vellox Agency",
				"is_standard": "No",
				"json": "{}",
			}
		).insert(ignore_permissions=True)
		self.assertFalse(can_run_report(copy.name, PM))
		self.assertTrue(can_run_report(copy.name, FINANCE))

	def test_project_expense_claim_totals_are_hidden(self):
		meta = frappe.get_meta("Project")
		if not meta.get_field("total_expense_claim"):
			self.skipTest("Frappe HR's total_expense_claim is not on this site")
		with self.set_user(PM):
			readable = set(frappe.new_doc("Project").get_permlevel_access("read"))
		self.assertNotIn(meta.get_field("total_expense_claim").permlevel, readable)

	def test_saving_through_the_client_api_returns_no_hidden_money(self):
		from vellox_agency.client_guard import save, set_value

		project = frappe.get_doc(
			{"doctype": "Project", "project_name": f"_Test RR {frappe.generate_hash(length=6)}", "company": "_Test Company"}
		).insert(ignore_permissions=True)
		# estimated_costing is typed in, so a save does not recalculate it.
		project.db_set("estimated_costing", 1234)
		# Frappe's filter empties hidden fields (as the desk form does).
		with self.set_user(PM):
			returned = set_value("Project", project.name, "notes", "checked")
			self.assertFalse(returned.get("estimated_costing"))
			doc = frappe.get_doc("Project", project.name).as_dict()
			self.assertFalse(save(doc).get("estimated_costing"))
		self.assertEqual(frappe.db.get_value("Project", project.name, "estimated_costing"), 1234)
		# Finance views projects (it does not edit them) and keeps the amounts.
		from vellox_agency.client_guard import _readable

		with self.set_user(FINANCE):
			self.assertEqual(_readable(frappe.get_doc("Project", project.name).as_dict()).get("estimated_costing"), 1234)


class TestTimesheetRates(_RatesCase):
	"""Rates come from Activity Cost for jobs that cannot see them (review of 378ffb3)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.tests.test_capacity import _employee

		if not frappe.db.exists("Gender", "Female"):
			frappe.get_doc({"doctype": "Gender", "gender": "Female"}).insert(ignore_permissions=True)
		cls.employee = _employee("RR Dev").name
		for activity, cost, bill in (("Developer", 41, 97), ("Designer", 11, 22)):
			frappe.db.set_value("Activity Type", activity, {"costing_rate": cost, "billing_rate": bill})
		frappe.get_doc(
			{"doctype": "Activity Cost", "employee": cls.employee, "activity_type": "Developer", "costing_rate": 41, "billing_rate": 97}
		).insert(ignore_permissions=True)

	_slot = 0

	def _next_slot(self):
		# A new day per timesheet: ERPNext refuses overlapping time for one employee.
		TestTimesheetRates._slot += 1
		return f"2026-11-{9 + TestTimesheetRates._slot:02d} 09:00:00"

	def _timesheet(self, activity, **row):
		return frappe.get_doc(
			{
				"doctype": "Timesheet",
				"employee": self.employee,
				"company": "_Test Company",
				"time_logs": [
					{"activity_type": activity, "from_time": self._next_slot(), "hours": 3, "is_billable": 1, **row}
				],
			}
		)

	def test_a_rate_typed_in_by_a_pm_is_replaced_by_the_real_one(self):
		with self.set_user(PM):
			ts = self._timesheet("Developer", costing_rate=999, billing_rate=999).insert(ignore_permissions=True)
		row = frappe.get_doc("Timesheet", ts.name).time_logs[0]
		self.assertEqual((row.costing_rate, row.billing_rate, row.costing_amount), (41, 97, 123))

	def test_changing_the_activity_takes_the_new_activitys_rate(self):
		ts = self._timesheet("Developer").insert(ignore_permissions=True)
		with self.set_user(PM):
			doc = frappe.get_doc("Timesheet", ts.name)
			doc.time_logs[0].activity_type = "Designer"
			doc.time_logs[0].costing_rate = 0
			doc.time_logs[0].billing_rate = 0
			doc.save(ignore_permissions=True)
		row = frappe.get_doc("Timesheet", ts.name).time_logs[0]
		self.assertEqual((row.activity_type, row.costing_rate, row.billing_rate), ("Designer", 11, 22))

	def _special_rate_timesheet(self):
		# Finance only views timesheets, so special rates come from a job with rate
		# access that edits them: the Agency Manager (here, a user with no job cap).
		return self._timesheet("Developer", costing_rate=50, billing_rate=120).insert(ignore_permissions=True)

	def test_a_job_with_rate_access_may_set_a_special_rate(self):
		row = frappe.get_doc("Timesheet", self._special_rate_timesheet().name).time_logs[0]
		self.assertEqual((row.costing_rate, row.billing_rate), (50, 120))

	def test_a_pm_editing_an_unchanged_row_keeps_its_special_rate(self):
		ts = self._special_rate_timesheet()
		with self.set_user(PM):
			doc = frappe.get_doc("Timesheet", ts.name)
			doc.note = "reviewed"
			doc.save(ignore_permissions=True)
		row = frappe.get_doc("Timesheet", ts.name).time_logs[0]
		self.assertEqual((row.costing_rate, row.billing_rate, row.costing_amount), (50, 120, 150))
