import frappe
from frappe.tests.utils import FrappeTestCase

from vellox_agency.crm_setup import setup_crm_intake_fields, setup_lead_assignment_and_sla


class TestLeadSLAQualification(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.tests.test_offer_builder import (
			_bootstrap_erpnext_test_fixtures,
		)

		_bootstrap_erpnext_test_fixtures()
		setup_crm_intake_fields()
		setup_lead_assignment_and_sla()

	def test_new_lead_gets_first_response_due_within_4_hours(self):
		from frappe.utils import add_to_date, now_datetime, get_datetime

		lead = frappe.get_doc(
			{
				"doctype": "Lead",
				"lead_name": "_Test SLA Lead",
				"email_id": "sla-lead@example.com",
			}
		).insert(ignore_permissions=True)

		due = get_datetime(lead.custom_vellox_first_response_due)
		expected = add_to_date(get_datetime(lead.creation), hours=4)
		self.assertIsNotNone(due)
		self.assertLessEqual(abs((due - expected).total_seconds()), 60)

	def test_assignment_rule_fixture_exists(self):
		rule = frappe.db.exists("Assignment Rule", "Vellox Intake Assignment")
		self.assertTrue(rule)
		doc = frappe.get_doc("Assignment Rule", rule)
		self.assertEqual(doc.document_type, "Lead")

	def test_opportunity_from_unqualified_lead_is_blocked(self):
		lead = frappe.get_doc(
			{
				"doctype": "Lead",
				"lead_name": "_Test Unqualified Lead",
				"email_id": "unqualified@example.com",
			}
		).insert(ignore_permissions=True)

		with self.assertRaisesRegex(frappe.ValidationError, "qualif"):
			frappe.get_doc(
				{
					"doctype": "Opportunity",
					"opportunity_from": "Lead",
					"party_name": lead.name,
					"company": "_Test Company",
				}
			).insert(ignore_permissions=True)

	def test_opportunity_from_qualified_lead_is_allowed(self):
		lead = frappe.get_doc(
			{
				"doctype": "Lead",
				"lead_name": "_Test Qualified Lead",
				"email_id": "qualified@example.com",
				"custom_vellox_qualified": 1,
			}
		).insert(ignore_permissions=True)

		opp = frappe.get_doc(
			{
				"doctype": "Opportunity",
				"opportunity_from": "Lead",
				"party_name": lead.name,
				"company": "_Test Company",
			}
		).insert(ignore_permissions=True)
		self.assertTrue(opp.name)
