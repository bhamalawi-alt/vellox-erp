import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from vellox_agency.crm_setup import (
	STAGE_PROBABILITY,
	setup_opportunity_pipeline,
)


def _unique(prefix):
	import secrets

	return f"{prefix}-{secrets.token_hex(4)}"


def _make_qualified_lead(email=None):
	email = email or f"{_unique('pipe')}@pipe.example.com"
	return frappe.get_doc(
		{
			"doctype": "Lead",
			"lead_name": email.split("@")[0],
			"email_id": email,
			"custom_vellox_qualified": 1,
		}
	).insert(ignore_permissions=True)


def _make_opportunity(lead_name=None, **extra):
	doc = {
		"doctype": "Opportunity",
		"opportunity_from": "Lead",
		"party_name": lead_name,
		"company": "_Test Company",
		"opportunity_type": "Sales",
	}
	doc.update(extra)
	return frappe.get_doc(doc).insert(ignore_permissions=True)


class TestOpportunityPipeline(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.tests.test_offer_builder import (
			_bootstrap_erpnext_test_fixtures,
		)

		_bootstrap_erpnext_test_fixtures()
		setup_opportunity_pipeline()

	def test_pipeline_stages_have_approved_probabilities(self):
		for stage, prob in STAGE_PROBABILITY.items():
			self.assertTrue(frappe.db.exists("Sales Stage", stage))
			self.assertEqual(
				frappe.db.get_value("Sales Stage", stage, "custom_vellox_probability"),
				prob,
				f"{stage} probability",
			)

	def test_stage_change_updates_probability(self):
		opp = _make_opportunity(
			_make_qualified_lead().name,
			sales_stage="Prospecting",
			opportunity_amount=100000,
			expected_close_date=add_days(nowdate(), 30),
		)
		self.assertEqual(opp.custom_vellox_probability, 10)
		opp.sales_stage = "Proposal Sent"
		opp.save()
		self.assertEqual(opp.custom_vellox_probability, 60)

	def test_lost_opportunity_requires_reason(self):
		opp = _make_opportunity(
			_make_qualified_lead().name,
			sales_stage="Negotiation",
			opportunity_amount=50000,
			expected_close_date=nowdate(),
		)
		opp.status = "Lost"
		with self.assertRaisesRegex(frappe.ValidationError, "lost reason"):
			opp.save()
		opp.reload()
		opp.status = "Lost"
		opp.append("lost_reasons", {"lost_reason": "Price"})
		opp.save()
		self.assertEqual(opp.status, "Lost")

	def test_weighted_pipeline_respects_permissions_and_currency(self):
		from vellox_agency.pipeline import weighted_pipeline

		limited = _unique("vellox-pipe") + "@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": limited,
				"first_name": "Pipe",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
		user_doc = frappe.get_doc("User", limited)
		user_doc.add_roles("Sales User")
		user_doc.save(ignore_permissions=True)

		customer_a = _unique("CustA")
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": customer_a,
				"customer_type": "Company",
				"customer_group": "_Test Vellox Client Group",
				"territory": "All Territories",
			}
		).insert(ignore_permissions=True)

		customer_b = _unique("CustB")
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": customer_b,
				"customer_type": "Company",
				"customer_group": "_Test Vellox Client Group",
				"territory": "All Territories",
			}
		).insert(ignore_permissions=True)

		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": limited,
				"allow": "Customer",
				"for_value": customer_a,
			}
		).insert(ignore_permissions=True)

		for customer, amount in ((customer_a, 100000), (customer_b, 900000)):
			_make_opportunity(
				None,
				opportunity_from="Customer",
				party_name=customer,
				sales_stage="Qualified",
				opportunity_amount=amount,
				expected_close_date=nowdate(),
				currency="USD",
				conversion_rate=1,
			)

		frappe.db.commit()
		result = weighted_pipeline(user=limited)
		entry = [r for r in result if r["currency"] == "USD"]
		self.assertTrue(entry, "expected USD weighted entry")
		self.assertEqual(entry[0]["weighted_total"], 30000)

	def test_stale_opportunities_query(self):
		from vellox_agency.pipeline import get_stale_opportunities

		opp = _make_opportunity(
			_make_qualified_lead().name,
			sales_stage="Prospecting",
			opportunity_amount=10000,
			expected_close_date=add_days(nowdate(), 7),
		)
		old = add_days(frappe.utils.now_datetime(), -30)
		frappe.db.set_value("Opportunity", opp.name, "modified", old, update_modified=False)
		stale_names = [r["name"] for r in get_stale_opportunities(days=14)]
		self.assertIn(opp.name, stale_names)
