import frappe
from frappe.tests.utils import FrappeTestCase

from vellox_agency.crm_setup import setup_quotation_estimate_fields
from vellox_agency.estimate import apply_estimate_margin, compute_margin


class TestEstimateMargin(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_quotation_estimate_fields()

	def test_margin_golden_cases(self):
		cases = [
			# (net_total, hours_json, vendor_cost, expected_pct)
			(100000, '[{"role":"PM","hours":10,"rate":500}]', 0, 95.0),
			(100000, '[{"role":"PM","hours":100,"rate":500},{"role":"Dev","hours":50,"rate":300}]', 5000, 30.0),
			(100000, None, 25000, 75.0),
			(0, '[{"role":"PM","hours":5,"rate":500}]', 0, 0.0),
		]
		for net_total, hours, vendor, expected in cases:
			with self.subTest(net_total=net_total, vendor=vendor):
				self.assertEqual(compute_margin(net_total, hours, vendor), expected)

	def test_invalid_hours_json_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			compute_margin(100000, "{not-json", 0)

	def test_quotation_validate_computes_and_never_touches_financials(self):
		from erpnext.selling.doctype.quotation.test_quotation import make_quotation
		from vellox_agency.tests.test_offer_builder import (
			TEST_CUSTOMER,
			TEST_PRICE_LIST,
		)

		item = "_Test Vellox Iso Service"
		if not frappe.db.exists("Item", item):
			from erpnext.stock.doctype.item.test_item import make_item

			make_item(item, {"is_stock_item": 0, "stock_uom": "Unit"})

		quotation = make_quotation(
			item=item,
			party_name=TEST_CUSTOMER,
			selling_price_list=TEST_PRICE_LIST,
			warehouse="",
			qty=1,
			rate=100000,
			do_not_save=True,
		)
		quotation.conversion_rate = 1
		quotation.calculate_taxes_and_totals()
		financials = (quotation.net_total, quotation.grand_total, quotation.items[0].rate)

		quotation.custom_vellox_estimate_hours = '[{"role":"PM","hours":20,"rate":500}]'
		quotation.custom_vellox_vendor_cost = 5000
		apply_estimate_margin(quotation)
		quotation.insert(ignore_permissions=True)

		self.assertEqual(quotation.custom_vellox_estimated_margin, 85.0)
		self.assertEqual(
			(quotation.net_total, quotation.grand_total, quotation.items[0].rate),
			financials,
		)
