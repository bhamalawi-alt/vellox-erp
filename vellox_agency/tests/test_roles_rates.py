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
