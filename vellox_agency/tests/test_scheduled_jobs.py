"""Scheduled jobs ([P3-100])."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_to_date, now_datetime, nowdate

from vellox_agency.tests.test_delivery_notifications import _outgoing_email_account

OWNER_A = "stale-owner-a@example.com"
OWNER_B = "stale-owner-b@example.com"
OPS = "stale-ops@example.com"


def _user(email, *roles):
	# Sales User only: a "Vellox Sales" user would join lead routing on the test site.
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": "Stale", "send_welcome_email": 0}).insert(
			ignore_permissions=True
		)
		frappe.get_doc("User", email).add_roles(*roles)
	return email


def _forget_cached_lead_routing():
	"""Earlier test classes roll back lead-routing changes, but Frappe's cached rule
	list can still show the rule as on with no users, which breaks Lead inserts."""
	from frappe.cache_manager import clear_doctype_map

	from vellox_agency.crm_setup import ASSIGNMENT_RULE

	clear_doctype_map("Assignment Rule", "Lead")
	frappe.clear_document_cache("Assignment Rule", ASSIGNMENT_RULE)


def _digests(subject):
	return frappe.get_all("Email Queue", filters={"message": ["like", f"%{subject}%"]}, fields=["name", "message"])


def _recipients(queue_name):
	return set(frappe.get_all("Email Queue Recipient", filters={"parent": queue_name}, pluck="recipient"))


class TestStaleOpportunityReminders(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.crm_setup import setup_opportunity_pipeline
		from vellox_agency.tests.test_offer_builder import _bootstrap_erpnext_test_fixtures

		_bootstrap_erpnext_test_fixtures()
		setup_opportunity_pipeline()
		_outgoing_email_account()
		_user(OWNER_A, "Sales User")
		_user(OWNER_B, "Sales User")

	def setUp(self):
		from vellox_agency.scheduled import reset_daily_guards

		frappe.db.delete("Email Queue")
		reset_daily_guards()
		_forget_cached_lead_routing()
		# Other modules' opportunities would land in these owners' lists otherwise.
		frappe.db.set_value("Opportunity", {"status": ["not in", ["Lost", "Closed", "Converted"]]}, "opportunity_owner", None)

	def _opportunity(self, owner, days_idle, **kw):
		from vellox_agency.tests.test_pipeline import _make_opportunity, _make_qualified_lead

		opp = _make_opportunity(
			_make_qualified_lead().name,
			sales_stage="Prospecting",
			opportunity_amount=1000,
			expected_close_date=add_days(nowdate(), 7),
			**kw,
		)
		frappe.db.set_value(
			"Opportunity",
			opp.name,
			{"opportunity_owner": owner, "modified": add_to_date(now_datetime(), days=-days_idle)},
			update_modified=False,
		)
		return opp.name

	def test_each_owner_gets_one_list_of_their_idle_opportunities(self):
		from vellox_agency.scheduled import send_stale_opportunity_reminders

		a_old, a_older = self._opportunity(OWNER_A, 20), self._opportunity(OWNER_A, 40)
		a_fresh = self._opportunity(OWNER_A, 2)
		b_old = self._opportunity(OWNER_B, 15)

		send_stale_opportunity_reminders()
		reminders = _digests("Opportunities with no update")
		by_owner = {frozenset(_recipients(r.name)): r.message for r in reminders}
		self.assertEqual(set(by_owner), {frozenset({OWNER_A}), frozenset({OWNER_B})})
		a_mail = by_owner[frozenset({OWNER_A})]
		self.assertIn(a_old, a_mail)
		self.assertIn(a_older, a_mail)
		self.assertNotIn(a_fresh, a_mail)
		self.assertNotIn(b_old, a_mail)
		self.assertIn(b_old, by_owner[frozenset({OWNER_B})])

	def test_lost_opportunities_are_left_out(self):
		from vellox_agency.scheduled import send_stale_opportunity_reminders

		lost = self._opportunity(OWNER_A, 30)
		frappe.db.set_value("Opportunity", lost, "status", "Lost", update_modified=False)
		send_stale_opportunity_reminders()
		self.assertEqual(_digests("Opportunities with no update"), [])

	def test_running_twice_in_a_day_sends_once(self):
		from vellox_agency.scheduled import send_stale_opportunity_reminders

		self._opportunity(OWNER_A, 20)
		send_stale_opportunity_reminders()
		send_stale_opportunity_reminders()
		self.assertEqual(len(_digests("Opportunities with no update")), 1)


class TestLateReplyDigestOnce(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.tests.test_offer_builder import _bootstrap_erpnext_test_fixtures

		_bootstrap_erpnext_test_fixtures()
		_outgoing_email_account()
		_user(OPS, "Vellox Operations")

	def setUp(self):
		from vellox_agency.scheduled import reset_daily_guards

		frappe.db.delete("Email Queue")
		reset_daily_guards()
		_forget_cached_lead_routing()

	def test_running_twice_in_a_day_sends_once(self):
		from vellox_agency.lead_followup import send_late_reply_digest

		lead = frappe.get_doc(
			{"doctype": "Lead", "lead_name": "Late twice", "email_id": f"late-{frappe.generate_hash(length=6)}@example.com"}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Lead", lead.name, "custom_vellox_first_response_due", add_to_date(now_datetime(), hours=-2))
		send_late_reply_digest()
		send_late_reply_digest()
		self.assertEqual(len(_digests("Leads waiting for a reply")), 1)


class TestSchedulerHooks(FrappeTestCase):
	def test_daily_jobs_are_scheduled(self):
		daily = frappe.get_hooks("scheduler_events")["daily"]
		self.assertIn("vellox_agency.scheduled.send_stale_opportunity_reminders", daily)
		self.assertIn("vellox_agency.lead_followup.send_late_reply_digest", daily)

	def test_scheduled_jobs_never_commit_part_way(self):
		# A commit inside a job would keep half its work if it then failed.
		jobs = [
			path
			for paths in frappe.get_hooks("scheduler_events").values()
			if isinstance(paths, list)
			for path in paths
			if path.startswith("vellox_agency.")
		]
		self.assertTrue(jobs)
		for path in jobs:
			with self.subTest(job=path), patch.object(frappe.db, "commit", side_effect=AssertionError("commit in job")):
				frappe.get_attr(path)()
