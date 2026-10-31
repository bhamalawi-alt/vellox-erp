"""Delivery rules hold however a record is saved, not only through transition() ([P3-146])."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, nowdate

TEAM = "enforce-team@example.com"
PM = "enforce-pm@example.com"


def _user(email, *roles):
	# No Vellox Sales / Agency Manager users: they join lead routing on the test site.
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": "Enforce", "send_welcome_email": 0}).insert(
			ignore_permissions=True
		)
		frappe.get_doc("User", email).add_roles(*roles)
	return email


class _EnforceCase(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.crm_setup import setup_change_request_doctype, setup_project_health_field
		from vellox_agency.delivery_setup import setup_delivery_fields
		from vellox_agency.tests.test_delivery_notifications import _outgoing_email_account
		from vellox_agency.tests.test_offer_builder import _bootstrap_erpnext_test_fixtures

		_bootstrap_erpnext_test_fixtures()
		setup_project_health_field()
		setup_change_request_doctype()
		setup_delivery_fields()
		_outgoing_email_account()
		_user(TEAM, "Vellox Team Member", "Projects User")
		_user(PM, "Vellox Project Manager", "Projects User", "Projects Manager")
		cls.project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"_Test Enforce {frappe.generate_hash(length=8)}",
				"company": "_Test Company",
				"expected_end_date": add_days(nowdate(), 30),
			}
		).insert(ignore_permissions=True)


class TestDeliverableSteps(_EnforceCase):
	def _deliverable(self, **kw):
		return frappe.get_doc(
			{
				"doctype": "Deliverable",
				"project": self.project.name,
				"title": f"Enforce {frappe.generate_hash(length=6)}",
				"deliverable_type": "Design",
				**kw,
			}
		).insert(ignore_permissions=True)

	def _set_status(self, doc, status):
		doc.reload()
		doc.status = status
		doc.save(ignore_permissions=True)
		return doc

	def _round(self, doc, audience, outcome):
		doc.reload()
		doc.append(
			"review_rounds",
			{"reviewer": "Administrator", "audience": audience, "outcome": outcome, "reviewed_on": frappe.utils.now_datetime()},
		)
		doc.save(ignore_permissions=True)

	def test_the_form_follows_the_review_steps(self):
		doc = self._deliverable()
		for status in ("Internal Review", "Client Review"):
			self._set_status(doc, status)
		self.assertEqual(frappe.db.get_value("Deliverable", doc.name, "status"), "Client Review")

	def test_a_draft_cannot_jump_to_approved(self):
		doc = self._deliverable()
		with self.assertRaisesRegex(frappe.ValidationError, "Draft"):
			self._set_status(doc, "Approved")

	def test_a_new_deliverable_starts_as_a_draft(self):
		with self.assertRaises(frappe.ValidationError):
			self._deliverable(status="Approved")

	def test_approval_needs_a_client_round_and_records_who_approved(self):
		doc = self._deliverable()
		for status in ("Internal Review", "Client Review"):
			self._set_status(doc, status)
		with self.assertRaisesRegex(frappe.ValidationError, "client review round"):
			self._set_status(doc, "Approved")
		self._round(doc, "Client", "Approved")
		self._set_status(doc, "Approved")
		approved = frappe.db.get_value("Deliverable", doc.name, ["accepted_by", "accepted_on"], as_dict=True)
		self.assertEqual(approved.accepted_by, "Administrator")
		self.assertTrue(approved.accepted_on)

	def test_an_approved_deliverable_cannot_be_reopened(self):
		doc = self._deliverable()
		for status in ("Internal Review", "Client Review"):
			self._set_status(doc, status)
		self._round(doc, "Client", "Approved")
		self._set_status(doc, "Approved")
		with self.assertRaises(frappe.ValidationError):
			self._set_status(doc, "Internal Review")

	def test_a_used_up_allowance_blocks_another_review_round(self):
		doc = self._deliverable(revision_allowance=0)
		self._set_status(doc, "Internal Review")
		self._round(doc, "Internal", "Changes Requested")
		self._set_status(doc, "Changes Requested")
		with self.assertRaisesRegex(frappe.ValidationError, "Change Request"):
			self._set_status(doc, "Internal Review")
		# After an approved Change Request a manager raises the allowance.
		doc.reload()
		doc.revision_allowance = 2
		doc.save(ignore_permissions=True)
		self._set_status(doc, "Internal Review")

	def test_the_engine_still_works(self):
		from vellox_agency.deliverable import transition

		doc = self._deliverable()
		for action in ("submit_for_review", "internal_approve"):
			transition(doc, action)
			doc.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Deliverable", doc.name, "status"), "Client Review")


class TestChangeRequestChecks(_EnforceCase):
	def _cr(self, **kw):
		return frappe.get_doc(
			{
				"doctype": "Vellox Change Request",
				"project": self.project.name,
				"title": f"Enforce CR {frappe.generate_hash(length=6)}",
				**kw,
			}
		)

	def test_a_new_request_cannot_start_approved(self):
		end = frappe.db.get_value("Project", self.project.name, "expected_end_date")
		with self.assertRaises(frappe.ValidationError):
			self._cr(status="Approved", schedule_impact_days=10).insert(ignore_permissions=True)
		self.assertEqual(getdate(frappe.db.get_value("Project", self.project.name, "expected_end_date")), getdate(end))

	def test_a_new_request_cannot_start_implemented(self):
		with self.assertRaises(frappe.ValidationError):
			self._cr(status="Implemented", price_impact=500).insert(ignore_permissions=True)

	def test_the_agency_manager_can_approve_a_request_with_no_price_change(self):
		# Delivery plan section 8: PM approves when the price is unchanged, the
		# Agency Manager approves any request.
		cr = self._cr(status="Draft").insert(ignore_permissions=True)
		cr.status = "Under Review"
		cr.save(ignore_permissions=True)
		cr.status = "Approved"
		with patch("vellox_agency.change_control._cr_roles", return_value={"Agency Manager"}):
			cr.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Vellox Change Request", cr.name, "status"), "Approved")

	def test_a_project_manager_cannot_approve_a_price_change(self):
		cr = self._cr(status="Draft", price_impact=1000).insert(ignore_permissions=True)
		cr.status = "Under Review"
		cr.save(ignore_permissions=True)
		cr.status = "Approved"
		with patch("vellox_agency.change_control._cr_roles", return_value={"Vellox Project Manager"}):
			with self.assertRaises(frappe.PermissionError):
				cr.save(ignore_permissions=True)


class TestProjectFromTemplate(_EnforceCase):
	TEMPLATE = "Vellox — Web Development"

	def test_a_team_member_cannot_create_a_project_from_a_template(self):
		from vellox_agency.acceptance import create_project_from_template

		with self.set_user(TEAM), self.assertRaises(frappe.PermissionError):
			create_project_from_template(self.TEMPLATE)

	def test_a_project_manager_can(self):
		from vellox_agency.acceptance import create_project_from_template

		with self.set_user(PM):
			self.assertTrue(create_project_from_template(self.TEMPLATE)["project"])

	def test_it_accepts_only_post(self):
		from vellox_agency.acceptance import create_project_from_template

		self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func.get(create_project_from_template), ["POST"])
