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
		from vellox_agency.api.intake import reset_rate_limit

		reset_rate_limit()
		frappe.db.delete("Lead", {"custom_vellox_source_url": "intake-test"})
		frappe.db.commit()

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

	def test_duplicate_within_24h_merges_into_existing_lead(self):
		with self.set_user("Guest"):
			first = _submit()["lead"]
			second = _submit(message="Second identical submission for the same prospect.")["lead"]
		self.assertEqual(first, second)
		self.assertEqual(
			frappe.db.count("Lead", {"email_id": "prospect@example.com"}), 1
		)
