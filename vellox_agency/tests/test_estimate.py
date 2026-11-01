"""Quote margin from Finance's role rates ([P3-143], owner 2026-11-01).

Sales enters roles and hours; each role's cost rate is the default rate
Finance sets on its Activity Type. Typed-in rates are ignored, a role with no
rate blocks the margin, and the labour cost is stored where only Finance and
the Agency Manager read it.
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from vellox_agency.crm_setup import setup_quotation_estimate_fields

ROLE_A = "_Test Vellox Estimator"
ROLE_B = "_Test Vellox Estimator 2"
UNPRICED = "_Test Vellox Unpriced Role"


def role_rate(role: str, rate: float) -> str:
	"""An Activity Type with this default cost rate (Finance's role rate)."""
	if not frappe.db.exists("Activity Type", role):
		frappe.get_doc({"doctype": "Activity Type", "activity_type": role}).insert(ignore_permissions=True)
	frappe.db.set_value("Activity Type", role, "costing_rate", rate)
	return role


def _quote(rate=100000, estimate=None, vendor=0, do_not_save=False):
	from erpnext.selling.doctype.quotation.test_quotation import make_quotation
	from erpnext.stock.doctype.item.test_item import make_item

	from vellox_agency.tests.test_offer_builder import TEST_CUSTOMER, TEST_PRICE_LIST

	item = "_Test Vellox Iso Service"
	if not frappe.db.exists("Item", item):
		make_item(item, {"is_stock_item": 0, "stock_uom": "Unit"})
	quotation = make_quotation(
		item=item,
		party_name=TEST_CUSTOMER,
		selling_price_list=TEST_PRICE_LIST,
		warehouse="",
		qty=1,
		rate=rate,
		currency="USD",
		do_not_save=True,
	)
	quotation.custom_vellox_estimate_hours = json.dumps(estimate) if estimate is not None else None
	quotation.custom_vellox_vendor_cost = vendor
	return quotation if do_not_save else quotation.insert(ignore_permissions=True)


class TestEstimateMargin(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.tests.test_offer_builder import _bootstrap_erpnext_test_fixtures

		_bootstrap_erpnext_test_fixtures()
		setup_quotation_estimate_fields()
		from vellox_agency.estimate import setup_labour_cost_field

		setup_labour_cost_field()
		role_rate(ROLE_A, 500)
		role_rate(ROLE_B, 300)
		role_rate(UNPRICED, 0)

	def _margin(self, net_total, rows, vendor=0):
		from vellox_agency.estimate import compute_margin

		result = compute_margin(net_total, json.dumps(rows), vendor)
		return result.labour, result.margin

	def test_margin_uses_finance_role_rates(self):
		cases = [
			# (net total, rows, vendor cost, expected labour, expected margin %)
			(100000, [{"role": ROLE_A, "hours": 10}], 0, 5000, 95.0),
			(100000, [{"role": ROLE_A, "hours": 100}, {"role": ROLE_B, "hours": 50}], 5000, 65000, 30.0),
			(100000, [], 25000, 0, 75.0),
			(0, [{"role": ROLE_A, "hours": 5}], 0, 2500, 0.0),
		]
		for net_total, rows, vendor, labour, margin in cases:
			with self.subTest(rows=rows, vendor=vendor):
				self.assertEqual(self._margin(net_total, rows, vendor), (labour, margin))

	def test_typed_rates_are_ignored(self):
		self.assertEqual(self._margin(100000, [{"role": ROLE_A, "hours": 10, "rate": 1}]), (5000, 95.0))

	def test_roles_match_in_any_letter_case(self):
		from vellox_agency.estimate import compute_margin

		result = compute_margin(100000, json.dumps([{"role": ROLE_A.upper(), "hours": 10}]), 0)
		self.assertEqual((result.labour, result.missing), (5000, []))
		self.assertEqual(result.rows, [{"role": ROLE_A, "hours": 10}])

	def test_a_role_without_a_rate_leaves_the_margin_unknown(self):
		from vellox_agency.estimate import compute_margin

		for role in (UNPRICED, "_Test No Such Role"):
			with self.subTest(role=role):
				result = compute_margin(100000, json.dumps([{"role": role, "hours": 1}]), 0)
				self.assertEqual((result.labour, result.margin, result.missing), (None, None, [role]))

	def test_rows_need_a_role_and_hours_that_are_real_numbers(self):
		from vellox_agency.estimate import compute_margin

		for raw, vendor in (
			(json.dumps([{"hours": 2}]), 0),
			(json.dumps([{"role": ROLE_A, "hours": -5}]), 0),
			(json.dumps([{"role": ROLE_A, "hours": float("nan")}]), 0),
			(json.dumps([{"role": ROLE_A, "hours": 1}]), -100),
		):
			with self.subTest(raw=raw, vendor=vendor):
				with self.assertRaises(frappe.ValidationError):
					compute_margin(100000, raw, vendor)

	def test_invalid_hours_json_is_rejected(self):
		from vellox_agency.estimate import compute_margin

		with self.assertRaises(frappe.ValidationError):
			compute_margin(100000, "{not-json", 0)

	def test_saving_a_quote_stores_rows_without_rates_and_the_hidden_cost(self):
		quote = _quote(estimate=[{"role": ROLE_A, "hours": 20, "rate": 1}], vendor=5000)
		self.assertEqual(quote.custom_vellox_estimated_margin, 85.0)
		self.assertEqual(quote.custom_vellox_estimated_labour_cost, 10000)
		self.assertEqual(json.loads(quote.custom_vellox_estimate_hours), [{"role": ROLE_A, "hours": 20}])
		self.assertEqual(quote.custom_vellox_margin_band, "40% or more")

	def test_a_draft_with_an_unpriced_role_saves_but_cannot_be_approved_or_submitted(self):
		from vellox_agency.approval import _approval_refusal, gate_submission

		quote = _quote(estimate=[{"role": UNPRICED, "hours": 3}])
		self.assertEqual(quote.custom_vellox_margin_band, "Unknown: cost rate missing")
		self.assertEqual(quote.custom_vellox_missing_rates, UNPRICED)
		self.assertIn("cost rate", _approval_refusal(quote)[0])
		with self.assertRaisesRegex(frappe.ValidationError, "cost rate"):
			gate_submission(quote)
		role_rate(UNPRICED, 10)
		self.addCleanup(role_rate, UNPRICED, 0)
		quote.save(ignore_permissions=True)
		self.assertFalse(quote.custom_vellox_missing_rates)
		self.assertEqual(quote.custom_vellox_estimated_labour_cost, 30)

	def test_margin_compares_company_currency_amounts(self):
		quote = _quote(rate=1000, estimate=[{"role": ROLE_A, "hours": 1}], do_not_save=True)
		quote.currency = "EGP"
		quote.conversion_rate = 0.02  # 1,000 EGP = 20 USD in the company's currency
		quote.plc_conversion_rate = 0.02
		quote.insert(ignore_permissions=True)
		self.assertEqual(quote.base_net_total, 20)
		self.assertEqual(quote.custom_vellox_estimated_margin, round((20 - 500) / 20 * 100, 2))

	def test_the_exact_margin_and_labour_cost_are_for_finance_and_the_agency_manager_only(self):
		from vellox_agency.estimate import LABOUR_COST_PERMLEVEL, LABOUR_COST_READERS

		meta = frappe.get_meta("Quotation")
		for field in ("custom_vellox_estimated_labour_cost", "custom_vellox_estimated_margin"):
			with self.subTest(field=field):
				self.assertEqual(meta.get_field(field).permlevel, LABOUR_COST_PERMLEVEL)
		self.assertEqual(meta.get_field("custom_vellox_margin_band").permlevel, 2)  # Sales and Operations
		# The margin frozen on a project is money too, with the quote's hours it would reveal rates.
		self.assertEqual(
			frappe.get_meta("Project").get_field("custom_vellox_expected_margin_percent").permlevel, 2
		)
		field = meta.get_field("custom_vellox_estimated_labour_cost")
		self.assertNotEqual(LABOUR_COST_PERMLEVEL, 2)  # the estimate panel's level, which Sales reads
		self.assertEqual(set(LABOUR_COST_READERS), {"Vellox Finance", "Agency Manager", "System Manager"})

	def test_the_quote_totals_are_never_touched(self):
		quote = _quote(do_not_save=True)
		quote.calculate_taxes_and_totals()
		financials = (quote.net_total, quote.grand_total, quote.items[0].rate)
		quote.custom_vellox_estimate_hours = json.dumps([{"role": ROLE_A, "hours": 20}])
		quote.insert(ignore_permissions=True)
		self.assertEqual((quote.net_total, quote.grand_total, quote.items[0].rate), financials)


class TestRateChanges(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.tests.test_offer_builder import _bootstrap_erpnext_test_fixtures

		_bootstrap_erpnext_test_fixtures()
		role_rate(ROLE_A, 500)

	def test_a_rate_change_since_the_last_save_stops_an_approval_with_a_clear_message(self):
		from vellox_agency.estimate import apply_estimate_margin

		quote = _quote(rate=1000, estimate=[{"role": ROLE_A, "hours": 1}])
		role_rate(ROLE_A, 600)
		self.addCleanup(role_rate, ROLE_A, 500)
		doc = frappe.get_doc("Quotation", quote.name)
		doc.flags.vellox_approving = True
		doc._doc_before_save = frappe.get_doc("Quotation", quote.name)
		with self.assertRaisesRegex(frappe.ValidationError, "Cost rates changed"):
			apply_estimate_margin(doc)

	def test_a_rate_change_does_not_make_the_next_saver_a_maker(self):
		from vellox_agency.approval import _terms_setters

		quote = _quote(rate=1000, estimate=[{"role": ROLE_A, "hours": 1}])
		role_rate(ROLE_A, 600)
		self.addCleanup(role_rate, ROLE_A, 500)
		other = "est-second-person@example.com"
		if not frappe.db.exists("User", other):
			frappe.get_doc({"doctype": "User", "email": other, "first_name": "Est", "send_welcome_email": 0}).insert(
				ignore_permissions=True
			)
			# ERPNext's own role only: Vellox job roles would join lead routing on the test site.
			frappe.get_doc("User", other).add_roles("Sales User")
		doc = frappe.get_doc("Quotation", quote.name)
		doc.terms = "Note"
		with self.set_user(other):
			doc.save(ignore_permissions=True)
		self.assertNotIn(other, _terms_setters(doc))


class TestNoEstimateNeedsApproval(FrappeTestCase):
	def test_zero_hours_are_no_estimate(self):
		from vellox_agency.approval import required_approver_role

		doc = frappe._dict(
			doctype="Quotation",
			net_total=100000,
			items=[frappe._dict(amount=100000)],
			custom_vellox_estimated_margin=100.0,
			custom_vellox_estimate_hours=json.dumps([{"role": ROLE_A, "hours": 0}]),
			custom_vellox_estimated_labour_cost=0,
			custom_vellox_vendor_cost=0,
		)
		self.assertEqual(required_approver_role(doc), "Vellox Operations")

	def test_a_quote_with_no_estimate_needs_operations(self):
		from vellox_agency.approval import required_approver_role

		for estimate, vendor in ((None, 0), ("[]", 0), ("", None)):
			with self.subTest(estimate=estimate, vendor=vendor):
				doc = frappe._dict(
					doctype="Quotation",
					net_total=100000,
					items=[frappe._dict(amount=100000)],
					custom_vellox_estimated_margin=100.0,
					custom_vellox_estimate_hours=estimate,
					custom_vellox_vendor_cost=vendor,
				)
				self.assertEqual(required_approver_role(doc), "Vellox Operations")

	def test_a_quote_with_an_estimate_can_still_be_auto_approved(self):
		from vellox_agency.approval import required_approver_role

		doc = frappe._dict(
			doctype="Quotation",
			net_total=100000,
			items=[frappe._dict(amount=100000)],
			custom_vellox_estimated_margin=60.0,
			custom_vellox_estimate_hours=json.dumps([{"role": ROLE_A, "hours": 10}]),
			custom_vellox_estimated_labour_cost=5000,
			custom_vellox_vendor_cost=0,
		)
		self.assertIsNone(required_approver_role(doc))
