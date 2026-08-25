import importlib

import frappe
from frappe.tests.utils import FrappeTestCase


class TestOfferBuilderSetup(FrappeTestCase):
	def test_custom_field_contract(self):
		try:
			module = importlib.import_module("vellox_agency.setup.offer_builder")
		except ModuleNotFoundError:
			self.fail("vellox_agency.setup.offer_builder must define the offer metadata")

		fields = module.get_offer_builder_custom_fields()
		self.assertEqual(
			[field["fieldname"] for field in fields["Item"]],
			[
				"custom_vellox_technical_proposal",
				"custom_vellox_default_duration",
				"custom_vellox_billing_method",
				"custom_vellox_project_template",
			],
		)
		self.assertEqual(
			[field["fieldname"] for field in fields["Quotation"]],
			[
				"custom_vellox_technical_proposal",
				"custom_vellox_proposal_item_signature",
			],
		)

	def test_setup_is_idempotent(self):
		module = importlib.import_module("vellox_agency.setup.offer_builder")
		module.setup_offer_builder()
		module.setup_offer_builder()

		self.assertEqual(
			frappe.get_meta("Item", cached=False).get_field("custom_vellox_billing_method").options,
			"Fixed Price\nMilestone\nRetainer\nTime and Materials",
		)
		self.assertEqual(
			frappe.get_meta("Quotation", cached=False)
			.get_field("custom_vellox_technical_proposal")
			.fieldtype,
			"Text Editor",
		)
