import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext.selling.doctype.quotation.test_quotation import make_quotation
from erpnext.stock.doctype.item.test_item import make_item
from vellox_agency.setup.offer_builder import setup_offer_builder


def _ensure(doctype, search_field, value, fields=None):
	if frappe.db.exists(doctype, {search_field: value}):
		return frappe.db.get_value(doctype, {search_field: value})
	doc = frappe.get_doc({"doctype": doctype, **(fields or {}), search_field: value})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return doc.name


def _bootstrap_erpnext_test_fixtures():
	"""Create the minimal masters ERPNext's make_item/make_quotation helpers expect.

	Everything is committed immediately: frappe's test runner rolls back between
	fixture objects, so uncommitted bootstrap records would be lost mid-run.
	"""
	_ensure("Currency", "currency_name", "EGP", {"enabled": 1, "symbol": "E£"})
	_ensure("UOM", "uom_name", "Unit")
	if not frappe.db.exists("Item Group", "All Item Groups"):
		frappe.get_doc(
			{"doctype": "Item Group", "item_group_name": "All Item Groups", "is_group": 1}
		).insert(ignore_permissions=True)
		frappe.db.commit()
	if not frappe.db.exists("Item Group", "Products"):
		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": "Products",
				"is_group": 0,
				"parent_item_group": "All Item Groups",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()

	if not frappe.db.a_row_exists("Company"):
		if not frappe.db.exists("Warehouse Type", "Transit"):
			frappe.get_doc({"doctype": "Warehouse Type", "name": "Transit"}).insert(
				ignore_permissions=True
			)
			frappe.db.commit()
		frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": "_Test Company",
				"abbr": "_TC",
				"default_currency": "USD",
				"country": "United States",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()

	_ensure(
		"Customer Group",
		"customer_group_name",
		"All Customer Groups",
		{"is_group": 1},
	)
	_ensure(
		"Customer Group",
		"customer_group_name",
		"_Test Vellox Client Group",
		{"is_group": 0, "parent_customer_group": "All Customer Groups"},
	)
	_ensure("Territory", "territory_name", "All Territories", {"is_group": 1})
	if not frappe.db.exists("Customer", "_Test Vellox Customer"):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": "_Test Vellox Customer",
				"customer_type": "Company",
				"customer_group": "_Test Vellox Client Group",
				"territory": "All Territories",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()

	if not frappe.db.exists("Price List", "_Test Vellox Selling"):
		frappe.get_doc(
			{
				"doctype": "Price List",
				"price_list_name": "_Test Vellox Selling",
				"selling": 1,
				"currency": "USD",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()


TEST_CUSTOMER = "_Test Vellox Customer"
TEST_PRICE_LIST = "_Test Vellox Selling"


class TestOfferBuilder(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_bootstrap_erpnext_test_fixtures()
		setup_offer_builder()

	def setUp(self):
		super().setUp()
		self.strategy = self.make_service(
			"_Test Vellox Strategy",
			"<p>Strategy proposal body</p>",
			duration="6 weeks",
			billing_method="Fixed Price",
		)
		self.design = self.make_service(
			"_Test Vellox Design",
			"<p>Design proposal body</p>",
			billing_method="Milestone",
		)

	def make_service(self, item_code, proposal, duration=None, billing_method=None):
		item = make_item(item_code, {"is_stock_item": 0, "stock_uom": "Unit"})
		item.custom_vellox_technical_proposal = proposal
		item.custom_vellox_default_duration = duration
		item.custom_vellox_billing_method = billing_method
		item.save()
		return item

	def test_composes_unique_sections_in_item_order(self):
		from vellox_agency.offer_builder.proposal import compose_technical_proposal

		result = compose_technical_proposal(
			[self.strategy.name, self.design.name, self.strategy.name]
		)
		self.assertLess(result["html"].index("Strategy proposal body"), result["html"].index("Design proposal body"))
		self.assertEqual(result["html"].count("Strategy proposal body"), 1)
		self.assertIn("6 weeks", result["html"])
		self.assertIn("Fixed Price", result["html"])
		self.assertNotIn("None", result["html"])
		self.assertEqual(result["item_signature"], '["_Test Vellox Strategy","_Test Vellox Design"]')

	def test_reports_service_without_template(self):
		from vellox_agency.offer_builder.proposal import compose_technical_proposal

		empty = self.make_service("_Test Vellox Empty", "")
		result = compose_technical_proposal([empty.name, self.design.name])
		self.assertEqual(result["skipped_items"], [empty.item_name])
		self.assertIn("Design proposal body", result["html"])

	def test_rejects_generation_when_no_service_has_a_template(self):
		from vellox_agency.offer_builder.proposal import compose_technical_proposal

		empty = self.make_service("_Test Vellox No Proposal", "")
		with self.assertRaisesRegex(frappe.ValidationError, "No selected service has a Technical Proposal Template"):
			compose_technical_proposal([empty.name])

	def make_quotation_doc(self, **args):
		return make_quotation(
			party_name=TEST_CUSTOMER,
			selling_price_list=TEST_PRICE_LIST,
			warehouse="",
			**args,
		)

	def test_rejects_submitted_quotation(self):
		from vellox_agency.offer_builder.proposal import build_technical_proposal

		quotation = self.make_quotation_doc(
			item=self.strategy.name,
			rate=100,
			do_not_submit=False,
		)
		with self.assertRaisesRegex(frappe.ValidationError, "draft Quotation"):
			build_technical_proposal(quotation.as_dict())

	def test_rejects_guest_user(self):
		from vellox_agency.offer_builder.proposal import build_technical_proposal

		quotation = self.make_quotation_doc(item=self.strategy.name, rate=100, do_not_submit=True)
		with self.set_user("Guest"), self.assertRaises(frappe.PermissionError):
			build_technical_proposal(quotation.as_dict())

	def test_generation_preserves_egp_and_usd_financial_values(self):
		from vellox_agency.offer_builder.proposal import build_technical_proposal

		for currency, rate in (("EGP", 5000), ("USD", 100)):
			with self.subTest(currency=currency):
				quotation = self.make_quotation_doc(
					item=self.strategy.name,
					rate=rate,
					currency=currency,
					do_not_save=True,
				)
				quotation.conversion_rate = 1
				quotation.price_list_currency = currency
				quotation.plc_conversion_rate = 1
				quotation.calculate_taxes_and_totals()
				financial_before = (quotation.currency, quotation.items[0].rate, quotation.grand_total)

				build_technical_proposal(quotation.as_dict())

				self.assertEqual(
					(quotation.currency, quotation.items[0].rate, quotation.grand_total),
					financial_before,
				)
