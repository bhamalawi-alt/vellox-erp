"""Budget used, forecast and profit per project ([P4-33], capacity plan sections 4 to 8).

The regression test is the plan's worked example (section 8): quoted USD 12,000,
budget 7,800 (frozen margin 35 %), cost so far 5,650, remaining 2,625, forecast
final cost 8,275, expected margin 31 %, drift -4 points, green.
"""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from vellox_agency.security import JOB_PROFILES

PM_USER = "pp-pm@example.com"
FIN_USER = "pp-finance@example.com"
OPS_USER = "pp-operations@example.com"


def _user(email, roles):
	# Never Sales or Agency Manager roles (they join lead routing on the test site).
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "PP", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
		frappe.get_doc("User", email).add_roles(*roles)
	return email


def _in_a_fiscal_year(day):
	"""Clean CI sites have no fiscal year for 2026; add one when it is missing."""
	from erpnext.accounts.utils import FiscalYearError, get_fiscal_year

	try:
		get_fiscal_year(day, company="_Test Company")
	except FiscalYearError:
		frappe.get_doc(
			{
				"doctype": "Fiscal Year",
				"year": "_Test Vellox FY 2026",
				"year_start_date": "2026-01-01",
				"year_end_date": "2026-12-31",
				"companies": [{"company": "_Test Company"}],
			}
		).insert(ignore_permissions=True)
	return day


class _ProfitCase(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.profit import setup_profit_fields
		from vellox_agency.security import setup_roles_and_permissions
		from vellox_agency.setup.roles_rates import setup_delivery_roles
		from vellox_agency.tests.test_capacity import _employee, setup_calendar_fixtures

		setup_calendar_fixtures()
		setup_delivery_roles()
		setup_roles_and_permissions()
		setup_profit_fields()
		frappe.db.set_single_value("Projects Settings", "ignore_employee_time_overlap", 1)
		_user(PM_USER, JOB_PROFILES["Project Manager"])
		_user(FIN_USER, JOB_PROFILES["Finance"])
		_user(OPS_USER, JOB_PROFILES["Operations"])
		cls.people, cls.rates = {}, {}
		for role, rate in (("Developer", 30), ("Designer", 25), ("Project Manager", 32.5)):
			user = _user(
				f"pp-{role.lower().replace(' ', '-')}-{frappe.generate_hash(length=4)}@example.com",
				["Projects User"],
			)
			employee = _employee(f"PP {role}", user_id=user).name
			frappe.get_doc(
				{
					"doctype": "Activity Cost",
					"employee": employee,
					"activity_type": role,
					"costing_rate": rate,
					"billing_rate": rate * 2,
				}
			).insert(ignore_permissions=True)
			cls.people[role] = (employee, user)
			cls.rates[role] = rate

	@classmethod
	def _quote(cls, amount=12000, estimate=None, vendor=600):
		from erpnext.selling.doctype.quotation.test_quotation import make_quotation
		from erpnext.stock.doctype.item.test_item import make_item

		from vellox_agency.approval import approve_quotation
		from vellox_agency.tests.test_offer_builder import TEST_CUSTOMER, TEST_PRICE_LIST

		item = "_Test Vellox Actions Service"
		if not frappe.db.exists("Item", item):
			make_item(item, {"is_stock_item": 0, "stock_uom": "Unit"})
		quote = make_quotation(
			item=item,
			party_name=TEST_CUSTOMER,
			selling_price_list=TEST_PRICE_LIST,
			warehouse="",
			qty=1,
			rate=amount,
			currency="USD",
			do_not_save=True,
		)
		quote.custom_vellox_estimate_hours = json.dumps(
			estimate
			or [
				{"role": "Developer", "hours": 120, "rate": 30},
				{"role": "Designer", "hours": 40, "rate": 25},
				{"role": "PM/QA", "hours": 80, "rate": 32.5},
			]
		)
		quote.custom_vellox_vendor_cost = vendor
		quote.insert(ignore_permissions=True)
		if quote.custom_vellox_approval_status != "Approved":
			approve_quotation(quote.name, seen=str(frappe.db.get_value("Quotation", quote.name, "modified")))
		quote = frappe.get_doc("Quotation", quote.name)
		quote.submit()
		return quote

	@classmethod
	def _project(cls, quote):
		return frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"_Test PP Web build {frappe.generate_hash(length=5)}",
				"company": "_Test Company",
				"custom_vellox_quotation": quote.name,
				"custom_vellox_expected_margin_percent": quote.custom_vellox_estimated_margin,
			}
		).insert(ignore_permissions=True)

	def _time(self, role, project, hours, day, billable_tick=1):
		employee, _user_id = self.people[role]
		ts = frappe.get_doc(
			{
				"doctype": "Timesheet",
				"employee": employee,
				"company": "_Test Company",
				"time_logs": [
					{
						"activity_type": role,
						"project": project,
						"from_time": f"{day} 09:00:00",
						"hours": hours,
						"is_billable": billable_tick,
						"costing_rate": self.rates[role],
					}
				],
			}
		).insert(ignore_permissions=True)
		ts.submit()
		return ts

	def _task(self, project, role, remaining):
		_employee, user = self.people[role]
		task = frappe.get_doc(
			{
				"doctype": "Task",
				"subject": f"PP {role}",
				"project": project,
				"custom_vellox_default_role": role,
				"custom_vellox_remaining_hours": remaining,
			}
		).insert(ignore_permissions=True)
		task.db_set("_assign", json.dumps([user]))
		return task


class TestWorkedExample(_ProfitCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.quote = cls._quote()
		cls.project = cls._project(cls.quote).name

	def _figures(self):
		from vellox_agency.profit import project_profit

		# Vendor invoices are standard Purchase Invoices; the example has 450 so far.
		with patch(
			"vellox_agency.profit._external_cost",
			side_effect=lambda names: ({n: [("USD", "2026-10-08", 450)] for n in names}, {}),
		):
			return project_profit(self.project)

	def test_the_plans_worked_example(self):
		self._time("Developer", self.project, 90, "2026-10-05")
		self._time("Designer", self.project, 35, "2026-10-06")
		self._time("Project Manager", self.project, 50, "2026-10-07")
		self._task(self.project, "Developer", 50)
		self._task(self.project, "Project Manager", 30)
		p = self._figures()
		self.assertEqual(p.contract_value, 12000)
		self.assertEqual(p.budget, 7800)
		self.assertAlmostEqual(p.frozen_margin, 35, places=2)
		self.assertEqual((p.time_cost, p.external_cost, p.cost_to_date), (5200, 450, 5650))
		self.assertEqual(p.remaining_cost, 2625)  # 50 x 30 + 30 x 32.50 + vendor 600 - 450
		self.assertEqual(p.forecast_cost, 8275)
		self.assertAlmostEqual(p.budget_used, 72.44, places=2)
		self.assertAlmostEqual(p.expected_margin, 31.04, places=2)
		self.assertAlmostEqual(p.margin_drift, -3.96, places=2)
		self.assertEqual(p.signal, "Green")
		self.assertEqual(p.unpriced_hours, 0)

	def _change_request(self, project, path):
		"""A request moved along `path` with real saves, as people would."""
		amendment = self._quote(1500, estimate=[{"role": "Developer", "hours": 20, "rate": 30}], vendor=0)
		request = frappe.get_doc(
			{
				"doctype": "Vellox Change Request",
				"project": project,
				"title": " > ".join(path),
				"price_impact": 1500,
				"amendment_quotation": amendment.name,
			}
		).insert(ignore_permissions=True)
		for status in path:
			request.status = status
			request.save(ignore_permissions=True, ignore_version=False)  # keep history, as outside tests
		return request

	def test_approved_and_implemented_change_requests_add_their_amendment_quote(self):
		# Owner, 2026-11-01 ([P4-35]): a request closed after it was implemented is a
		# finished change and counts; one closed straight from Approved was withdrawn.
		from vellox_agency.profit import project_profit

		project = self._project(self._quote()).name
		for path in (
			["Under Review", "Approved"],
			["Under Review", "Approved", "Implemented"],
			["Under Review", "Approved", "Implemented", "Closed"],
			["Under Review", "Approved", "Closed"],
			["Under Review", "Rejected"],
		):
			self._change_request(project, path)
		p = project_profit(project)
		self.assertEqual(p.contract_value, 12000 + 3 * 1500)
		self.assertEqual(p.budget, 7800 + 3 * 600)

	def test_implemented_on_is_set_by_the_server_only(self):
		project = self._project(self._quote()).name
		done = self._change_request(project, ["Under Review", "Approved", "Implemented"])
		self.assertEqual(str(done.implemented_on), frappe.utils.nowdate())
		withdrawn = self._change_request(project, ["Under Review", "Approved"])
		withdrawn.implemented_on = "2026-10-01"  # sent by a client
		withdrawn.status = "Closed"
		withdrawn.save(ignore_permissions=True)
		self.assertIsNone(frappe.db.get_value("Vellox Change Request", withdrawn.name, "implemented_on"))

	def test_the_patch_fills_implemented_on_from_history(self):
		from vellox_agency.patches.backfill_change_request_implemented_on import execute

		project = self._project(self._quote()).name
		done = self._change_request(project, ["Under Review", "Approved", "Implemented", "Closed"])
		withdrawn = self._change_request(project, ["Under Review", "Approved", "Closed"])
		for request in (done, withdrawn):
			request.db_set("implemented_on", None)  # as on a site upgraded from before [P4-35]
		execute()
		self.assertIsNotNone(frappe.db.get_value("Vellox Change Request", done.name, "implemented_on"))
		self.assertIsNone(frappe.db.get_value("Vellox Change Request", withdrawn.name, "implemented_on"))

	def test_quotes_in_another_currency_use_the_rate_on_their_date(self):
		from vellox_agency.profit import project_profit, projects_profit

		quote = self._quote()
		frappe.db.set_value("Quotation", quote.name, {"currency": "EGP", "transaction_date": "2026-10-10"})
		frappe.get_doc(
			{
				"doctype": "Currency Exchange",
				"date": "2026-10-01",
				"from_currency": "EGP",
				"to_currency": "USD",
				"exchange_rate": 0.02,
				"for_selling": 1,
			}
		).insert(ignore_permissions=True)
		project = self._project(quote).name
		p = project_profit(project)
		self.assertAlmostEqual(p.contract_value, 240)  # 12,000 EGP x 0.02
		self.assertAlmostEqual(p.budget, 156)

		# A quote dated before any rate: a note for that project, the others still work.
		older = self._quote()
		frappe.db.set_value("Quotation", older.name, {"currency": "EGP", "transaction_date": "2026-09-01"})
		missing = self._project(older).name
		results, errors = projects_profit([project, missing])
		self.assertIn(project, results)
		self.assertIn("exchange rate", errors[missing])
		self.assertFalse([m for m in frappe.local.message_log if "exchange" in str(m)])  # no pop-ups

	def test_remaining_hours_skip_closed_tasks_and_fall_back_to_the_role_rate(self):
		from vellox_agency.profit import project_profit

		project = self._project(self._quote(vendor=0)).name
		self._task(project, "Developer", 10).db_set("status", "Completed")
		frappe.db.set_value("Activity Type", "Designer", "costing_rate", 20)
		frappe.get_doc(
			{
				"doctype": "Task",
				"subject": "PP unassigned",
				"project": project,
				"custom_vellox_default_role": "Designer",
				"custom_vellox_remaining_hours": 5,
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Task",
				"subject": "PP no role",
				"project": project,
				"custom_vellox_remaining_hours": 3,
			}
		).insert(ignore_permissions=True)
		p = project_profit(project)
		self.assertEqual(p.remaining_cost, 100)  # 5 h x the Designer default 20; the completed task is out
		self.assertEqual(p.unpriced_hours, 3)


class TestSignal(FrappeTestCase):
	def test_owner_thresholds(self):
		from vellox_agency.profit import profit_signal

		cases = [
			# (expected margin %, drift points, forecast cost, contract) -> signal
			((31, -4, 8275, 12000), "Green"),
			((24, -2, 9000, 12000), "Amber"),  # under 25 %
			((30, -11, 8400, 12000), "Amber"),  # more than 10 points below the quote
			((9, -2, 10900, 12000), "Red"),  # under 10 %
			((-5, -40, 12600, 12000), "Red"),  # forecast cost over the price
		]
		for args, expected in cases:
			with self.subTest(args=args):
				self.assertEqual(profit_signal(*args), expected)


class TestProfitOnProjects(_ProfitCase):
	def test_vendor_invoices_count_as_external_cost(self):
		from vellox_agency.profit import project_profit

		project = self._project(self._quote()).name
		supplier = "_Test Vellox Hosting Vendor"
		if not frappe.db.exists("Supplier", supplier):
			group = (
				frappe.db.get_value("Supplier Group", {"is_group": 0})
				or frappe.get_doc(
					{"doctype": "Supplier Group", "supplier_group_name": "_Test Vellox Vendors"}
				)
				.insert(ignore_permissions=True)
				.name
			)
			frappe.get_doc(
				{"doctype": "Supplier", "supplier_name": supplier, "supplier_group": group}
			).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"company": "_Test Company",
				"posting_date": _in_a_fiscal_year("2026-10-20"),
				"set_posting_time": 1,
				"supplier": supplier,
				"currency": "USD",
				"credit_to": "Creditors - _TC",
				"items": [
					{
						"item_code": "_Test Vellox Actions Service",
						"qty": 1,
						"rate": 450,
						"project": project,
						"expense_account": "Cost of Goods Sold - _TC",
						"cost_center": "Main - _TC",
					}
				],
			}
		).insert(ignore_permissions=True).submit()
		p = project_profit(project)
		self.assertEqual(p.external_cost, 450)
		self.assertEqual(p.remaining_cost, 150)  # vendor cost still to come

	def test_the_daily_refresh_stores_percentages_and_colour_only(self):
		from vellox_agency.profit import refresh_project_profit

		project = self._project(self._quote()).name
		self._time("Developer", project, 20, "2026-10-12")
		refresh_project_profit()
		stored = frappe.db.get_value(
			"Project",
			project,
			["custom_vellox_budget_used", "custom_vellox_margin_drift", "custom_vellox_profit_signal"],
			as_dict=True,
		)
		self.assertAlmostEqual(stored.custom_vellox_budget_used, 600 / 7800 * 100, places=2)
		self.assertEqual(stored.custom_vellox_profit_signal, "Green")

	def test_operations_reads_the_stored_health_fields_and_pms_and_team_members_do_not(self):
		from vellox_agency.profit import PROFIT_PERMLEVEL

		meta = frappe.get_meta("Project")
		for field in (
			"custom_vellox_budget_used",
			"custom_vellox_margin_drift",
			"custom_vellox_profit_signal",
		):
			with self.subTest(field=field):
				self.assertEqual(meta.get_field(field).permlevel, PROFIT_PERMLEVEL)
		team_user = _user("pp-team@example.com", JOB_PROFILES["Team Member"])
		self.assertIn(PROFIT_PERMLEVEL, meta.get_permlevel_access("read", user=OPS_USER))
		self.assertIn(PROFIT_PERMLEVEL, meta.get_permlevel_access("read", user=FIN_USER))
		# PMs edit every project; they see their own projects' figures in the report.
		self.assertNotIn(PROFIT_PERMLEVEL, meta.get_permlevel_access("read", user=PM_USER))
		self.assertNotIn(PROFIT_PERMLEVEL, meta.get_permlevel_access("read", user=team_user))

	def test_the_refresh_runs_daily(self):
		self.assertIn(
			"vellox_agency.profit.refresh_project_profit", frappe.get_hooks("scheduler_events")["daily"]
		)

	def test_only_pms_and_operations_change_remaining_hours(self):
		# Owner, 2026-11-01 ([P4-35]): team members see it; it feeds the forecast.
		from vellox_agency.profit import REMAINING_HOURS_PERMLEVEL

		meta = frappe.get_meta("Task")
		self.assertEqual(meta.get_field("custom_vellox_remaining_hours").permlevel, REMAINING_HOURS_PERMLEVEL)
		team_user = _user("pp-team@example.com", JOB_PROFILES["Team Member"])
		for user in (PM_USER, OPS_USER):
			with self.subTest(user=user):
				self.assertIn(REMAINING_HOURS_PERMLEVEL, meta.get_permlevel_access("write", user=user))
		self.assertIn(REMAINING_HOURS_PERMLEVEL, meta.get_permlevel_access("read", user=team_user))
		self.assertNotIn(REMAINING_HOURS_PERMLEVEL, meta.get_permlevel_access("write", user=team_user))

	def test_a_team_members_save_keeps_the_pms_remaining_hours(self):
		team_user = _user("pp-team@example.com", JOB_PROFILES["Team Member"])
		project = frappe.get_doc("Project", self._project(self._quote()).name)
		project.append("users", {"user": team_user})
		project.save(ignore_permissions=True)
		task = self._task(project.name, "Developer", 12)
		with self.set_user(team_user):
			doc = frappe.get_doc("Task", task.name)
			doc.custom_vellox_remaining_hours = 1
			doc.description = "Working on it"
			doc.save()
		self.assertEqual(frappe.db.get_value("Task", task.name, "custom_vellox_remaining_hours"), 12)
		self.assertEqual(frappe.db.get_value("Task", task.name, "description"), "Working on it")

	def test_remaining_hours_live_on_tasks(self):
		self.assertEqual(
			frappe.get_meta("Task").get_field("custom_vellox_remaining_hours").fieldtype, "Float"
		)


class TestProfitReport(_ProfitCase):
	REPORT = "Vellox Project Profit"

	def _run(self, user):
		from vellox_agency.vellox_agency_projects.report.vellox_project_profit.vellox_project_profit import (
			execute,
		)

		with self.set_user(user):
			columns, rows = execute({})
		return {c["fieldname"] for c in columns}, rows

	def test_finance_sees_the_amounts(self):
		self._project(self._quote())
		columns, rows = self._run(FIN_USER)
		self.assertTrue({"contract_value", "cost_to_date", "forecast_cost", "expected_margin"} <= columns)
		self.assertTrue(rows)

	def test_project_managers_see_percentages_and_colour_but_no_amounts(self):
		own = self._project(self._quote())
		own.db_set("custom_vellox_project_manager", PM_USER)
		other = self._project(self._quote()).name
		columns, rows = self._run(PM_USER)
		self.assertIn(own.name, {r["project"] for r in rows})
		self.assertNotIn(other, {r["project"] for r in rows})  # own projects only
		self.assertTrue({"budget_used", "margin_drift", "signal"} <= columns)
		self.assertFalse(
			{"contract_value", "cost_to_date", "forecast_cost", "remaining_cost", "budget", "expected_margin"}
			& columns
		)
		for row in rows:
			self.assertFalse(
				{
					"contract_value",
					"cost_to_date",
					"forecast_cost",
					"remaining_cost",
					"budget",
					"expected_margin",
				}
				& set(row)
			)

	def test_operations_sees_every_project_without_amounts(self):
		own = self._project(self._quote())
		own.db_set("custom_vellox_project_manager", PM_USER)
		columns, rows = self._run(OPS_USER)
		self.assertIn(own.name, {r["project"] for r in rows})
		self.assertNotIn("contract_value", columns)

	def test_team_members_cannot_run_it(self):
		from vellox_agency.report_guard import can_run_report

		with patch("vellox_agency.security._job_roles", return_value={"Vellox Team Member"}):
			self.assertFalse(can_run_report(self.REPORT, "someone@example.com"))


class TestUtilization(_ProfitCase):
	def test_billable_hours_over_available_hours(self):
		from vellox_agency.capacity import week_capacity

		employee, _user_id = self.people["Designer"]
		project = self._project(self._quote()).name
		self._time("Designer", project, 8, "2026-11-09")
		self._time("Designer", project, 8, "2026-11-12")
		week = week_capacity(employee, "2026-11-09")
		self.assertEqual(week["billable_hours"], 16)
		self.assertAlmostEqual(week["utilization"], 16 / 32 * 100, places=2)

	def test_billable_means_client_projects_not_the_tick(self):
		# Owner, 2026-11-01 ([P4-35]): hours on any project not marked Internal are
		# billable, ticked or not; internal projects and rows without a project are not.
		from vellox_agency.capacity import week_capacity

		employee, _user_id = self.people["Developer"]
		client = self._project(self._quote()).name
		internal = self._project(self._quote())
		internal.db_set("custom_vellox_internal", 1)
		self._time("Developer", client, 6, "2026-11-09", billable_tick=0)
		self._time("Developer", internal.name, 4, "2026-11-10")
		self._time("Developer", None, 2, "2026-11-12")
		week = week_capacity(employee, "2026-11-09")
		self.assertEqual(week["billable_hours"], 6)

	def test_projects_carry_an_internal_checkbox(self):
		self.assertEqual(frappe.get_meta("Project").get_field("custom_vellox_internal").fieldtype, "Check")
