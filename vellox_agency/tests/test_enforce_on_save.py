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

	def _cr(self, **kw):
		return frappe.get_doc(
			{
				"doctype": "Vellox Change Request",
				"project": self.project.name,
				"title": f"Enforce CR {frappe.generate_hash(length=6)}",
				**kw,
			}
		)


class TestDeliverableSteps(_EnforceCase):
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


class TestDeliverableRoles(_EnforceCase):
	"""Delivery plan sections 5 and 8: Project Managers and the Agency Manager send work to
	the client, record the client's answer and approve; others cannot, however they save."""

	def _to_client_review(self):
		doc = self._deliverable()
		for status in ("Internal Review", "Client Review"):
			self._set_status(doc, status)
		return doc

	def test_a_team_member_cannot_send_work_to_the_client(self):
		doc = self._deliverable()
		self._set_status(doc, "Internal Review")
		with self.set_user(TEAM), self.assertRaises(frappe.PermissionError):
			self._set_status(doc, "Client Review")

	def test_a_team_member_cannot_record_the_client_answer_or_approve(self):
		doc = self._to_client_review()
		with self.set_user(TEAM):
			with self.assertRaises(frappe.PermissionError):
				self._round(doc, "Client", "Approved")
			doc.reload()
			doc.append(
				"review_rounds",
				{"reviewer": TEAM, "audience": "Client", "outcome": "Approved", "reviewed_on": frappe.utils.now_datetime()},
			)
			doc.status = "Approved"
			with self.assertRaises(frappe.PermissionError):
				doc.save(ignore_permissions=True)

	def test_a_project_manager_approves_and_is_recorded_as_the_approver(self):
		doc = self._to_client_review()
		with self.set_user(PM):
			self._round(doc, "Client", "Approved")
			doc.reload()
			doc.status = "Approved"
			doc.accepted_by = "Guest"  # read-only on the form; a client could still send it
			doc.accepted_on = "2020-01-01 00:00:00"
			doc.save(ignore_permissions=True)
		approved = frappe.db.get_value("Deliverable", doc.name, ["accepted_by", "accepted_on"], as_dict=True)
		self.assertEqual(approved.accepted_by, PM)
		self.assertGreater(getdate(approved.accepted_on), getdate("2020-01-01"))

	def test_review_rounds_cannot_be_removed_or_changed(self):
		doc = self._deliverable()
		self._round(doc, "Internal", "Changes Requested")
		doc.reload()
		doc.review_rounds[0].outcome = "Approved"
		with self.assertRaisesRegex(frappe.ValidationError, "Review rounds"):
			doc.save(ignore_permissions=True)
		doc.reload()
		doc.set("review_rounds", [])
		with self.assertRaisesRegex(frappe.ValidationError, "Review rounds"):
			doc.save(ignore_permissions=True)

	def test_only_managers_change_the_revision_allowance(self):
		doc = self._deliverable()
		with self.set_user(TEAM):
			doc.reload()
			doc.revision_allowance = 99
			with self.assertRaises(frappe.PermissionError):
				doc.save(ignore_permissions=True)
		with self.set_user(PM):
			doc.reload()
			doc.revision_allowance = 5
			doc.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Deliverable", doc.name, "revision_allowance"), 5)

	def test_a_copy_starts_fresh(self):
		doc = self._to_client_review()
		self._round(doc, "Client", "Approved")
		self._set_status(doc, "Approved")
		# As the form's Duplicate does: fields marked no_copy are left out.
		copy = frappe.copy_doc(frappe.get_doc("Deliverable", doc.name), ignore_no_copy=False).insert(
			ignore_permissions=True
		)
		self.assertEqual(copy.status, "Draft")
		self.assertEqual(copy.review_rounds, [])
		self.assertFalse(copy.accepted_by or copy.accepted_on)


class TestChangeRequestIntegrity(_EnforceCase):
	def _end(self):
		return getdate(frappe.db.get_value("Project", self.project.name, "expected_end_date"))

	def _approved(self, days=5, **kw):
		cr = self._cr(status="Draft", schedule_impact_days=days, **kw).insert(ignore_permissions=True)
		cr.status = "Under Review"
		cr.save(ignore_permissions=True)
		cr.status = "Approved"
		cr.save(ignore_permissions=True)
		return cr

	def test_a_blank_status_counts_as_draft(self):
		cr = self._cr(status="").insert(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Vellox Change Request", cr.name, "status"), "Draft")
		cr.reload()
		cr.status = "Implemented"
		cr.price_impact = 100
		with self.assertRaises(frappe.ValidationError):
			cr.save(ignore_permissions=True)

	def test_clearing_the_status_cannot_skip_the_checks(self):
		cr = self._cr(status="Draft").insert(ignore_permissions=True)
		cr.status = "Under Review"
		cr.save(ignore_permissions=True)
		cr.status = ""
		with self.assertRaises(frappe.ValidationError):  # Under Review -> Draft is not a move
			cr.save(ignore_permissions=True)

	def test_the_end_date_moves_exactly_once(self):
		start = self._end()
		cr = self._approved(days=5)
		self.assertEqual(self._end(), getdate(add_days(start, 5)))
		for _ in range(2):
			cr.reload()
			cr.approved_by = None  # read-only on the form; a client could still send it
			cr.save(ignore_permissions=True)
		self.assertEqual(self._end(), getdate(add_days(start, 5)))

	def test_a_spoofed_approver_neither_blocks_the_shift_nor_sticks(self):
		start = self._end()
		cr = self._cr(status="Draft", schedule_impact_days=3).insert(ignore_permissions=True)
		cr.status = "Under Review"
		cr.save(ignore_permissions=True)
		cr.status = "Approved"
		cr.approved_by = "spoof"
		cr.save(ignore_permissions=True)
		self.assertEqual(self._end(), getdate(add_days(start, 3)))
		self.assertEqual(frappe.db.get_value("Vellox Change Request", cr.name, "approved_by"), "Administrator")


class TestApprovalRecordIsKept(_EnforceCase):
	def test_who_approved_a_deliverable_cannot_be_changed_later(self):
		doc = self._deliverable()
		for status in ("Internal Review", "Client Review"):
			self._set_status(doc, status)
		self._round(doc, "Client", "Approved")
		self._set_status(doc, "Approved")
		before = frappe.db.get_value("Deliverable", doc.name, ["accepted_by", "accepted_on"], as_dict=True)
		with self.set_user(TEAM):
			doc.reload()
			doc.accepted_by = "Guest"
			doc.accepted_on = "2020-01-01 00:00:00"
			doc.save(ignore_permissions=True)
		after = frappe.db.get_value("Deliverable", doc.name, ["accepted_by", "accepted_on"], as_dict=True)
		self.assertEqual(after, before)

	def test_sending_client_work_back_needs_the_clients_answer(self):
		doc = self._deliverable()
		for status in ("Internal Review", "Client Review"):
			self._set_status(doc, status)
		with self.assertRaisesRegex(frappe.ValidationError, "client review round"):
			self._set_status(doc, "Changes Requested")
		self._round(doc, "Client", "Changes Requested")
		self._set_status(doc, "Changes Requested")

	def test_who_approved_a_change_request_cannot_be_changed_later(self):
		cr = self._cr(status="Draft").insert(ignore_permissions=True)
		for status in ("Under Review", "Approved"):
			cr.status = status
			cr.save(ignore_permissions=True)
		with self.set_user(TEAM):
			cr.reload()
			cr.approved_by = "spoof"
			cr.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Vellox Change Request", cr.name, "approved_by"), "Administrator")

	def test_old_blank_statuses_become_draft(self):
		from vellox_agency.patches import change_request_blank_status

		cr = self._cr(status="Draft").insert(ignore_permissions=True)
		frappe.db.set_value("Vellox Change Request", cr.name, "status", "", update_modified=False)
		change_request_blank_status.execute()
		self.assertEqual(frappe.db.get_value("Vellox Change Request", cr.name, "status"), "Draft")
