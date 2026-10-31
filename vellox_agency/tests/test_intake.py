from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from vellox_agency.crm_setup import setup_crm_intake_fields
from vellox_agency.setup.commercial import PRACTICES

SERVICES = [PRACTICES[0]["item_code"], PRACTICES[2]["item_code"]]


def _submit(**overrides):
	from vellox_agency.api.intake import submit_inquiry

	payload = {
		"full_name": "Test Prospect",
		"email": "prospect@example.com",
		"phone": "+20 100 000 0000",
		"company": "Prospect Co",
		"services": SERVICES,
		"message": "We need a full rebrand for our fintech startup this quarter.",
		"consent": 1,
		"source_url": "intake-test",
		"website_url": "",
	}
	payload.update(overrides)
	return submit_inquiry(**payload)


class TestIntake(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_crm_intake_fields()

	def setUp(self):
		super().setUp()
		from vellox_agency.api.intake import reset_all_rate_limits

		reset_all_rate_limits()
		frappe.db.delete("Lead", {"custom_vellox_source_url": "intake-test"})
		frappe.db.commit()
		# If a lead gets assigned, the assignment email would commit mid-test.
		patcher = patch("frappe.desk.form.assign_to.notify_assignment")
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_logged_in_visitor_keeps_their_session(self):
		# The intake writes as Administrator internally; the caller's request
		# session must come back intact, or their real session is overwritten.
		session = frappe.local.session
		before = (session.user, session.sid, dict(session.data))
		session.sid, session.data = "REALSID123", frappe._dict(csrf_token="token-abc")
		try:
			_submit(email="logged-in@example.com")
			self.assertEqual(frappe.session.user, before[0])
			self.assertEqual(frappe.local.session.sid, "REALSID123")
			self.assertEqual(frappe.local.session.data.get("csrf_token"), "token-abc")
		finally:
			frappe.local.session.sid, frappe.local.session.data = before[1], frappe._dict(before[2])

	def test_happy_path_creates_lead_with_consent_and_services(self):
		with self.set_user("Guest"):
			res = _submit()
		lead = frappe.get_doc("Lead", res["lead"])
		self.assertEqual(lead.email_id, "prospect@example.com")
		self.assertEqual(lead.custom_vellox_consent, 1)
		self.assertEqual(frappe.parse_json(lead.custom_vellox_services), SERVICES)
		self.assertEqual(lead.custom_vellox_source_url, "intake-test")
		self.assertIn("rebrand", lead.custom_vellox_inquiry)

	def test_invalid_payload_is_rejected(self):
		with self.set_user("Guest"):
			with self.assertRaises(frappe.ValidationError):
				_submit(email="not-an-email")
			with self.assertRaises(frappe.ValidationError):
				_submit(services=["VEL-NOT-A-PRACTICE"])
			with self.assertRaises(frappe.ValidationError):
				_submit(consent=0)

	def test_honeypot_discards_silently(self):
		with self.set_user("Guest"):
			res = _submit(website_url="http://spam.example")
		before = frappe.db.count("Lead")
		self.assertTrue(res["ok"])
		self.assertIsNone(res["lead"])
		self.assertEqual(frappe.db.count("Lead"), before)

	def test_rate_limit_blocks_sixth_inquiry_per_ip(self):
		from frappe.exceptions import TooManyRequestsError

		with self.set_user("Guest"):
			for i in range(5):
				_submit(email=f"lead{i}@example.com")
			with self.assertRaises(TooManyRequestsError):
				_submit(email="lead6@example.com")

	def _from_ip(self, ip, reset=True):
		from vellox_agency.api.intake import reset_rate_limit

		if reset:
			reset_rate_limit(ip)
		previous = getattr(frappe.local, "request_ip", None)
		frappe.local.request_ip = ip
		self.addCleanup(setattr, frappe.local, "request_ip", previous)
		self.addCleanup(reset_rate_limit, ip)

	def test_each_visitor_has_their_own_limit(self):
		# [P3-145]: one visitor using up the limit must not block everyone else.
		from frappe.exceptions import TooManyRequestsError

		self._from_ip("203.0.113.9")
		with self.set_user("Guest"):
			for i in range(5):
				_submit(email=f"busy{i}@example.com")
			with self.assertRaises(TooManyRequestsError):
				_submit(email="busy6@example.com")

			self._from_ip("198.51.100.7")
			self.assertTrue(_submit(email="other-visitor@example.com")["lead"])

	def test_the_limit_is_keyed_on_the_request_address(self):
		from vellox_agency.api.intake import _client_ip

		self._from_ip("192.0.2.44")
		self.assertEqual(_client_ip(), "192.0.2.44")

	def test_addresses_in_one_ipv6_network_share_a_limit(self):
		# A home or server connection gets a whole /64, so any one visitor can use
		# billions of IPv6 addresses; the limit treats the /64 as one visitor.
		from frappe.exceptions import TooManyRequestsError

		with self.set_user("Guest"):
			self._from_ip("2001:db8:1:1::1")
			for i in range(5):
				self._from_ip(f"2001:db8:1:1::{i + 1:x}", reset=False)
				_submit(email=f"v6-{i}@example.com")
			self._from_ip("2001:db8:1:1::ff", reset=False)
			with self.assertRaises(TooManyRequestsError):
				_submit(email="v6-6@example.com")
			self._from_ip("2001:db8:1:2::1")
			self.assertTrue(_submit(email="v6-other@example.com")["lead"])

	def test_one_mailbox_cannot_be_flooded_through_address_variants(self):
		# name+tag@ and Gmail's dotted spellings reach one inbox; each new Lead
		# would send it an acknowledgement email.
		from frappe.exceptions import TooManyRequestsError

		from vellox_agency.api.intake import MAX_PER_ADDRESS

		with self.set_user("Guest"):
			for i in range(MAX_PER_ADDRESS):
				self._from_ip(f"203.0.113.{i + 1}")
				_submit(email=f"victim+{i}@example.com")
			self._from_ip("203.0.113.200")
			with self.assertRaises(TooManyRequestsError):
				_submit(email="Victim+again@Example.com")

	def test_gmail_dots_and_tags_count_as_one_address(self):
		from vellox_agency.api.intake import _mailbox

		self.assertEqual(_mailbox("J.Doe+offer@gmail.com"), _mailbox("jdoe@googlemail.com"))
		self.assertEqual(_mailbox("j.doe+x@example.com"), "j.doe@example.com")

	def test_every_limit_key_expires(self):
		# The window is set before counting, so a crash between the two steps can
		# never leave a counter that blocks a visitor forever.
		from vellox_agency.api.intake import _ip_key

		self._from_ip("192.0.2.10")
		with self.set_user("Guest"):
			_submit(email="ttl@example.com")
		cache = frappe.cache()
		self.assertGreater(cache.ttl(_ip_key("192.0.2.10")), 0)

	def test_a_returning_client_after_a_day_is_added_to_their_lead(self):
		# ERPNext refuses a second Lead with the same email, so a later inquiry must
		# join the existing one instead of being lost.
		with self.set_user("Guest"):
			first = _submit(email="returning@example.com")["lead"]
		frappe.db.set_value(
			"Lead", first, "creation", frappe.utils.add_to_date(frappe.utils.now_datetime(), days=-3)
		)
		self._from_ip("198.51.100.20")
		with self.set_user("Guest"):
			second = _submit(email="returning@example.com", message="Back again with a new project for you.")["lead"]
		self.assertEqual(first, second)
		self.assertIn("Back again", frappe.db.get_value("Lead", first, "custom_vellox_inquiry"))

	def test_duplicate_within_24h_merges_into_existing_lead(self):
		with self.set_user("Guest"):
			first = _submit()["lead"]
			second = _submit(message="Second identical submission for the same prospect.")["lead"]
		self.assertEqual(first, second)
		self.assertEqual(
			frappe.db.count("Lead", {"email_id": "prospect@example.com"}), 1
		)
