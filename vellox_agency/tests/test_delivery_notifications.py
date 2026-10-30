import frappe
from frappe.tests.utils import FrappeTestCase

from vellox_agency.crm_setup import setup_project_health_field
from vellox_agency.deliverable import transition
from vellox_agency.delivery_setup import NOTIFICATION_DEFINITIONS, setup_delivery_fields

OWNER = "notify-owner@example.com"
MANAGER = "notify-manager@example.com"


def _user(email, role):
	if not frappe.db.exists("User", email):
		user = frappe.get_doc({"doctype": "User", "email": email, "first_name": "Notify", "send_welcome_email": 0})
		user.insert(ignore_permissions=True)
		user.add_roles(role)
	return email


def _outgoing_email_account():
	"""Frappe refuses to queue mail without a default outgoing account; SMTP is not contacted in tests."""
	if not frappe.db.exists("Email Account", {"default_outgoing": 1}):
		frappe.get_doc(
			{
				"doctype": "Email Account",
				"email_account_name": "_Test Vellox Outgoing",
				"email_id": "notify-sender@example.com",
				"enable_outgoing": 1,
				"default_outgoing": 1,
				"smtp_server": "smtp.example.com",
			}
		).insert(ignore_permissions=True)


def _queued(doc):
	"""Return (subject line, recipients) for every email queued against doc."""
	queued = []
	for row in frappe.get_all(
		"Email Queue",
		filters={"reference_doctype": doc.doctype, "reference_name": doc.name},
		fields=["name", "message"],
		order_by="creation asc",
	):
		recipients = frappe.get_all("Email Queue Recipient", filters={"parent": row.name}, pluck="recipient")
		queued.append((row.message, set(recipients)))
	return queued


def _subjects(doc):
	return [message for message, _ in _queued(doc)]


class TestDeliveryNotifications(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.tests.test_offer_builder import _bootstrap_erpnext_test_fixtures

		_bootstrap_erpnext_test_fixtures()
		setup_delivery_fields()
		setup_project_health_field()
		frappe.reload_doctype("Deliverable")
		frappe.reload_doctype("Vellox Change Request")
		_outgoing_email_account()
		_user(OWNER, "Agency Staff")
		_user(MANAGER, "Agency Manager")
		existing = frappe.db.get_value("Project", {"project_name": "_Test Notify Project"})
		cls.project = (
			frappe.get_doc("Project", existing)
			if existing
			else frappe.get_doc(
				{"doctype": "Project", "project_name": "_Test Notify Project", "company": "_Test Company"}
			).insert(ignore_permissions=True)
		)

	def _deliverable(self, **kw):
		with self.set_user(OWNER):
			return frappe.get_doc(
				{
					"doctype": "Deliverable",
					"project": self.project.name,
					"title": frappe.generate_hash(length=8),
					"deliverable_type": "Design",
					**kw,
				}
			).insert(ignore_permissions=True)

	def _move(self, doc, *actions):
		for action in actions:
			transition(doc, action)
			doc.save(ignore_permissions=True)
		return doc

	def _client_round(self, doc, outcome):
		doc.append(
			"review_rounds",
			{
				"reviewer": "Administrator",
				"audience": "Client",
				"outcome": outcome,
				"reviewed_on": frappe.utils.now_datetime(),
			},
		)
		doc.save(ignore_permissions=True)

	def test_client_review_emails_the_owner(self):
		doc = self._move(self._deliverable(), "submit_for_review", "internal_approve")
		queued = _queued(doc)
		self.assertEqual(len(queued), 1, queued)
		message, recipients = queued[0]
		self.assertIn("Deliverable sent to client review", message)
		self.assertEqual(recipients, {OWNER})

	def test_resaving_without_status_change_sends_nothing_new(self):
		doc = self._move(self._deliverable(), "submit_for_review", "internal_approve")
		doc.reload()
		doc.description = "Edited after review started"
		doc.save(ignore_permissions=True)
		self.assertEqual(len(_queued(doc)), 1)

	def test_client_approval_emails_the_decision(self):
		doc = self._move(self._deliverable(), "submit_for_review", "internal_approve")
		self._client_round(doc, "Approved")
		self._move(doc, "client_approve")
		self.assertTrue(any("Client decision on" in s for s in _subjects(doc)), _subjects(doc))

	def test_exhausted_revision_allowance_emails_agency_managers(self):
		doc = self._move(self._deliverable(revision_allowance=0), "submit_for_review", "internal_approve")
		self._client_round(doc, "Changes Requested")
		self._move(doc, "request_changes")
		exhausted = [r for m, r in _queued(doc) if "Revision allowance exhausted" in m]
		self.assertEqual(len(exhausted), 1, _queued(doc))
		self.assertIn(MANAGER, exhausted[0])

	def test_change_request_decision_emails_the_owner_once(self):
		with self.set_user(OWNER):
			cr = frappe.get_doc(
				{"doctype": "Vellox Change Request", "title": "Extra page", "project": self.project.name}
			).insert(ignore_permissions=True)
		for status in ("Under Review", "Approved"):
			cr.reload()
			cr.status = status
			cr.save(ignore_permissions=True)
		cr.reload()
		cr.save(ignore_permissions=True)
		decisions = [r for m, r in _queued(cr) if "Change Request" in m and "Approved" in m]
		self.assertEqual(len(decisions), 1, _queued(cr))
		self.assertEqual(decisions[0], {OWNER})

	def test_setup_repairs_existing_method_notifications(self):
		name = NOTIFICATION_DEFINITIONS[0]["name"]
		frappe.db.set_value(
			"Notification",
			name,
			{"event": "Method", "method": "vellox_agency.notifications.notify_client_review"},
		)
		setup_delivery_fields()
		notification = frappe.get_doc("Notification", name)
		self.assertEqual(notification.event, "Value Change")
		self.assertEqual(notification.value_changed, "status")
		self.assertFalse(notification.method)
