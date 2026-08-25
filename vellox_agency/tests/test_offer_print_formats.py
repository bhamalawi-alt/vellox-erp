import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext.selling.doctype.quotation.test_quotation import make_quotation
from erpnext.stock.doctype.item.test_item import make_item
from vellox_agency.setup.offer_builder import setup_offer_builder


class TestOfferPrintFormats(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_offer_builder()

	def test_three_offer_formats_render_expected_sections(self):
		item = make_item("_Test Vellox Print Service", {"is_stock_item": 0, "stock_uom": "Unit"})
		quotation = make_quotation(
			item=item.name,
			party_name="_Test Vellox Customer",
			selling_price_list="_Test Vellox Selling",
			warehouse="",
			rate=2500,
			do_not_submit=True,
		)
		quotation.custom_vellox_technical_proposal = "<p>Client-specific technical content</p>"
		quotation.save()

		technical = frappe.get_print("Quotation", quotation.name, "Vellox Technical Offer", no_letterhead=1)
		financial = frappe.get_print("Quotation", quotation.name, "Vellox Financial Offer", no_letterhead=1)
		combined = frappe.get_print("Quotation", quotation.name, "Vellox Combined Offer", no_letterhead=1)

		self.assertIn("Client-specific technical content", technical)
		self.assertNotIn("Grand Total", technical)
		self.assertIn(item.item_name, financial)
		self.assertIn("Grand Total", financial)
		self.assertNotIn("Client-specific technical content", financial)
		self.assertIn("Client-specific technical content", combined)
		self.assertIn("Grand Total", combined)
