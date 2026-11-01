"""Customer billing and unpaid figures: Finance and the Agency Manager only ([P3-142]).

Owner decision 2026-11-01, matching P3-140's "hide money and cost data".
"""

from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

USER = "cm-viewer@example.com"
FIGURES = [{"company": "_Test Company", "billing_this_year": 1200, "total_unpaid": 300, "currency": "USD"}]


@contextmanager
def _as_job(*jobs):
	with patch("vellox_agency.security._job_roles", return_value=set(jobs)):
		yield


class TestCustomerMoney(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.tests.test_offer_builder import TEST_CUSTOMER, _bootstrap_erpnext_test_fixtures

		_bootstrap_erpnext_test_fixtures()
		cls.customer = TEST_CUSTOMER
		# Only Sales User: the job is patched per test, so no user joins lead routing.
		if not frappe.db.exists("User", USER):
			frappe.get_doc({"doctype": "User", "email": USER, "first_name": "CM", "send_welcome_email": 0}).insert(
				ignore_permissions=True
			)
			frappe.get_doc("User", USER).add_roles("Sales User")

	def _figures_seen(self, *jobs):
		with (
			patch("erpnext.selling.doctype.customer.customer.get_dashboard_info", return_value=FIGURES),
			self.set_user(USER),
			_as_job(*jobs),
		):
			doc = frappe.get_doc("Customer", self.customer)
			doc.run_method("onload")
			return doc.get_onload().get("dashboard_info")

	def test_finance_and_the_agency_manager_see_the_figures(self):
		for job in ("Vellox Finance", "Agency Manager"):
			with self.subTest(job=job):
				self.assertEqual(self._figures_seen(job), FIGURES)

	def test_other_jobs_open_the_customer_without_the_figures(self):
		for job in ("Vellox Sales", "Vellox Project Manager", "Vellox Operations"):
			with self.subTest(job=job):
				self.assertEqual(self._figures_seen(job), [])

	def test_a_finance_job_alongside_another_still_sees_them(self):
		self.assertEqual(self._figures_seen("Vellox Sales", "Vellox Finance"), FIGURES)

	def test_users_without_a_job_keep_erpnexts_view(self):
		self.assertEqual(self._figures_seen(), FIGURES)

	def test_the_hook_runs_after_erpnexts_own_onload(self):
		self.assertIn("vellox_agency.security.hide_customer_money", frappe.get_hooks("doc_events")["Customer"]["onload"])

	def test_the_real_project_manager_profile_is_hidden_from(self):
		from vellox_agency.security import JOB_PROFILES

		pm = "cm-pm@example.com"
		if not frappe.db.exists("User", pm):
			frappe.get_doc({"doctype": "User", "email": pm, "first_name": "CM", "send_welcome_email": 0}).insert(
				ignore_permissions=True
			)
			frappe.get_doc("User", pm).add_roles(*JOB_PROFILES["Project Manager"])
		with (
			patch("erpnext.selling.doctype.customer.customer.get_dashboard_info", return_value=FIGURES),
			self.set_user(pm),
		):
			doc = frappe.get_doc("Customer", self.customer)
			doc.run_method("onload")
			self.assertEqual(doc.get_onload().get("dashboard_info"), [])
