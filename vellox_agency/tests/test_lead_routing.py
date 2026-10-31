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
		for patcher in (
			patch("vellox_agency.crm_setup.LEAD_ROSTER_ROLES", (self.seller, self.fallback)),
			# Assignment emails go through the email queue, which commits; muting
			# them keeps each test inside its rolled-back transaction.
			patch("frappe.desk.form.assign_to.notify_assignment"),
		):
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

	def test_users_restricted_by_user_permissions_are_left_out(self):
		restricted = _user(self._email("routing-restricted"), self.seller, LEAD_READER)
		frappe.get_doc(
			{"doctype": "User Permission", "user": restricted, "allow": "Company", "for_value": "_Test Company"}
		).insert(ignore_permissions=True)
		open_seller = _user(self._email("routing-open"), self.seller, LEAD_READER)
		self.assertEqual([u.user for u in _rule().users], [open_seller])

	def test_disabled_users_are_left_out(self):
		seller = _user(self._email("routing-disabled"), self.seller, LEAD_READER)
		frappe.db.set_value("User", seller, "enabled", 0)
		sync_lead_assignment_users()
		self.assertNotIn(seller, [u.user for u in _rule().users])

	def test_website_inquiry_survives_an_assignee_without_full_access(self):
		# The case that lost inquiries: Frappe shares a lead with an assignee who
		# cannot see it, and the share check ran as Guest.
		from vellox_agency.api.intake import reset_rate_limit, submit_inquiry
		from vellox_agency.setup.commercial import PRACTICES

		blind = _user(self._email("routing-blind"), self.seller)  # cannot read Lead
		rule = _rule()
		rule.set("users", [{"user": blind}])  # e.g. Lead read revoked after the last sync
		rule.disabled = 0
		rule.save(ignore_permissions=True)
		reset_rate_limit()
		with self.set_user("Guest"):
			res = submit_inquiry(
				full_name="Routing Prospect",
				email=self._email("routing-prospect"),
				services=[PRACTICES[0]["item_code"]],
				message="We need a new identity for our clinic network.",
				consent=1,
				website_url="",
			)
		self.assertTrue(res["ok"])
		self.assertTrue(frappe.db.exists("Lead", res["lead"]))
		self.assertEqual(self._assignees(res["lead"]), [blind])  # the share path really ran
		self.assertTrue(frappe.db.exists("DocShare", {"share_name": res["lead"], "user": blind}))

	def test_setup_replaces_an_administrator_only_rule(self):
		seller = _user(self._email("routing-after-migrate"), self.seller, LEAD_READER)
		# The state on sites installed before this fix, written without firing
		# any hook, so only the setup step can repair it.
		frappe.db.delete("Assignment Rule User", {"parent": ASSIGNMENT_RULE})
		frappe.get_doc(
			{
				"doctype": "Assignment Rule User",
				"parent": ASSIGNMENT_RULE,
				"parenttype": "Assignment Rule",
				"parentfield": "users",
				"user": "Administrator",
			}
		).db_insert()
		frappe.db.set_value("Assignment Rule", ASSIGNMENT_RULE, "disabled", 0, update_modified=False)
		frappe.clear_document_cache("Assignment Rule", ASSIGNMENT_RULE)
		self.assertEqual([u.user for u in _rule().users], ["Administrator"])

		setup_lead_assignment_and_sla()
		self.assertEqual([u.user for u in _rule().users], [seller])
