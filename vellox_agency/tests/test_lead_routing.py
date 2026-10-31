from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from vellox_agency.crm_setup import (
	ASSIGNMENT_RULE,
	setup_crm_intake_fields,
	setup_lead_assignment_and_sla,
	sync_lead_assignment_users,
)

# Fresh test-only roles stand in for ("Vellox Sales", "Agency Manager") in every
# test, so the tests never change who holds the real roles and are not affected
# by rows an earlier local run may have left behind.
LEAD_READER = "Sales User"  # ERPNext role that can read Lead


def _role(name):
	if not frappe.db.exists("Role", name):
		frappe.get_doc({"doctype": "Role", "role_name": name, "desk_access": 1}).insert(ignore_permissions=True)


def _user(email, *roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "Routing", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	frappe.get_doc("User", email).add_roles(*roles)
	return email


def _rule():
	return frappe.get_doc("Assignment Rule", ASSIGNMENT_RULE)


class TestLeadRouting(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.tests.test_offer_builder import _bootstrap_erpnext_test_fixtures

		_bootstrap_erpnext_test_fixtures()
		setup_crm_intake_fields()
		setup_lead_assignment_and_sla()

	def setUp(self):
		self.tag = frappe.generate_hash(length=8)
		self.seller = f"_Test Lead Seller {self.tag}"
		self.fallback = f"_Test Lead Fallback {self.tag}"
		_role(self.seller)
		_role(self.fallback)
		patcher = patch("vellox_agency.crm_setup.LEAD_ROSTER_ROLES", (self.seller, self.fallback))
		patcher.start()
		self.addCleanup(patcher.stop)

	def _email(self, name):
		return f"{name}-{self.tag}@example.com"

	def _assignees(self, lead):
		return frappe.get_all(
			"ToDo",
			filters={"reference_type": "Lead", "reference_name": lead, "status": "Open"},
			pluck="allocated_to",
		)

	def test_new_lead_goes_to_a_salesperson_not_administrator(self):
		seller = _user(self._email("routing-seller"), self.seller, LEAD_READER)
		rule = _rule()
		self.assertEqual([u.user for u in rule.users], [seller])
		self.assertFalse(rule.disabled)

		lead = frappe.get_doc(
			{"doctype": "Lead", "lead_name": "_Test Routed Lead", "email_id": self._email("routed-lead")}
		).insert(ignore_permissions=True)
		self.assertEqual(self._assignees(lead.name), [seller])

	def test_website_inquiry_as_guest_is_assigned_without_errors(self):
		seller = _user(self._email("routing-guest-seller"), self.seller, LEAD_READER)
		with self.set_user("Guest"):
			lead = frappe.get_doc(
				{"doctype": "Lead", "lead_name": "_Test Guest Lead", "email_id": self._email("guest-lead")}
			).insert(ignore_permissions=True)
		self.assertEqual(self._assignees(lead.name), [seller])

	def test_users_who_cannot_read_leads_are_left_out(self):
		_user(self._email("routing-no-access"), self.seller)
		manager = _user(self._email("routing-manager"), self.fallback, LEAD_READER)
		self.assertEqual([u.user for u in _rule().users], [manager])

	def test_roster_follows_the_role(self):
		seller = _user(self._email("routing-moves"), self.seller, LEAD_READER)
		self.assertIn(seller, [u.user for u in _rule().users])
		frappe.get_doc("User", seller).remove_roles(self.seller)
		self.assertNotIn(seller, [u.user for u in _rule().users])

	def test_without_anyone_to_route_to_the_rule_is_disabled(self):
		sync_lead_assignment_users()
		rule = _rule()
		self.assertEqual([u.user for u in rule.users], [])
		self.assertTrue(rule.disabled)
		self.assertNotIn("Administrator", [u.user for u in rule.users])
