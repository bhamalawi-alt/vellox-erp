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


def _user(email, roles):
	# Never Sales or Agency Manager roles (they join lead routing on the test site).
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "PP", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
		frappe.get_doc("User", email).add_roles(*roles)
	return email


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
			approve_quotation(quote.name)
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

	def _time(self, role, project, hours, day):
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
						"is_billable": 1,
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
			"vellox_agency.profit._external_cost", side_effect=lambda names: dict.fromkeys(names, 450)
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

	def test_an_approved_change_request_adds_its_amendment_quote(self):
		from vellox_agency.profit import project_profit

		project = self._project(self._quote()).name
		amendment = self._quote(3000, estimate=[{"role": "Developer", "hours": 40, "rate": 30}], vendor=0)
		for status in ("Approved", "Rejected"):
			request = frappe.get_doc(
				{
					"doctype": "Vellox Change Request",
					"project": project,
					"title": f"Extra pages {status}",
					"price_impact": 3000,
					"amendment_quotation": amendment.name,
				}
			).insert(ignore_permissions=True)
			request.db_set("status", status)
		p = project_profit(project)
		self.assertEqual(p.contract_value, 15000)  # the rejected one is not counted
		self.assertEqual(p.budget, 7800 + 1200)


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

	def test_project_managers_read_the_health_fields_and_team_members_do_not(self):
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
		self.assertIn(PROFIT_PERMLEVEL, meta.get_permlevel_access("read", user=PM_USER))
		self.assertNotIn(PROFIT_PERMLEVEL, meta.get_permlevel_access("read", user=team_user))

	def test_the_refresh_runs_daily(self):
		self.assertIn(
			"vellox_agency.profit.refresh_project_profit", frappe.get_hooks("scheduler_events")["daily"]
		)

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
