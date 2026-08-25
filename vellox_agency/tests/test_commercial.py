import frappe
from frappe.tests.utils import FrappeTestCase

from vellox_agency.setup.commercial import (
	EGP_PRICE_LIST,
	PRACTICES,
	USD_PRICE_LIST,
	setup_commercial_foundation,
)


class TestCommercialFoundation(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.tests.test_offer_builder import (
			_bootstrap_erpnext_test_fixtures,
		)

		_bootstrap_erpnext_test_fixtures()
		setup_commercial_foundation()

	def test_seven_practices_exist_as_non_stock_service_items(self):
		self.assertEqual(len(PRACTICES), 7)
		for practice in PRACTICES:
			item = frappe.get_doc("Item", practice["item_code"])
			self.assertEqual(item.is_stock_item, 0)
			self.assertEqual(item.item_group, "Vellox Services")

	def test_dual_currency_price_lists_and_item_prices(self):
		for price_list, currency in (
			(EGP_PRICE_LIST, "EGP"),
			(USD_PRICE_LIST, "USD"),
		):
			pl = frappe.get_doc("Price List", price_list)
			self.assertEqual(pl.currency, currency)
			self.assertEqual(pl.selling, 1)

		for practice in PRACTICES:
			for price_list in (EGP_PRICE_LIST, USD_PRICE_LIST):
				self.assertTrue(
					frappe.db.exists(
						"Item Price",
						{"item_code": practice["item_code"], "price_list": price_list},
					),
					f"missing {price_list} price for {practice['item_code']}",
				)

	def test_quotation_prices_each_service_in_egp_and_usd(self):
		from erpnext.selling.doctype.quotation.test_quotation import make_quotation
		from vellox_agency.tests.test_offer_builder import TEST_CUSTOMER

		item = PRACTICES[0]["item_code"]
		for price_list, rate_key in ((EGP_PRICE_LIST, "egp"), (USD_PRICE_LIST, "usd")):
			expected_rate = frappe.db.get_value(
				"Item Price",
				{"item_code": item, "price_list": price_list},
				"price_list_rate",
			)
			self.assertTrue(expected_rate)

			quotation = make_quotation(
				item=item,
				party_name=TEST_CUSTOMER,
				selling_price_list=price_list,
				warehouse="",
				rate=expected_rate,
				currency="EGP" if rate_key == "egp" else "USD",
				conversion_rate=1,
				do_not_submit=True,
			)
			self.assertEqual(quotation.items[0].rate, expected_rate)
