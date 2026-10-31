import frappe
from frappe.tests.utils import FrappeTestCase

from vellox_agency.approval import gate_submission, required_approver_role
from vellox_agency.crm_setup import setup_commercial_approval_fields


def _doc(net_total=100000, gross=100000, margin=50.0):
	return frappe._dict(
		doctype="Quotation",
		net_total=net_total,
		items=[frappe._dict(amount=gross)],
		custom_vellox_estimated_margin=margin,
		custom_vellox_approval_status="Pending",
		custom_vellox_approved_by=None,
	)


class TestCommercialApproval(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_commercial_approval_fields()

	def test_routing_matrix(self):
		cases = [
			# (discount%, margin, expected role)
			(3, 50.0, None),
			(5, 40.0, None),
			(10, 30.0, "Vellox Operations"),
			(15, 25.0, "Vellox Operations"),
			(10, 10.0, "Agency Manager"),
			(30, 60.0, "Agency Manager"),
		]
		for discount, margin, expected in cases:
			gross = 100000
			net = round(gross * (1 - discount / 100.0), 2)
			doc = _doc(net_total=net, gross=gross, margin=margin)
			with self.subTest(discount=discount, margin=margin):
				self.assertEqual(required_approver_role(doc), expected)

	def test_unapproved_submission_is_blocked(self):
		doc = _doc(net_total=80000, gross=100000, margin=10.0)  # needs Agency Manager
		with self.assertRaisesRegex(frappe.ValidationError, "commercial approval"):
			gate_submission(doc)

	def test_auto_band_stamps_approval_on_validate(self):
		# Stamping now reads the saved approval, so it needs a real quotation.
		from vellox_agency.tests.test_offer_builder import _bootstrap_erpnext_test_fixtures
		from vellox_agency.tests.test_quotation_actions import _real_quote

		_bootstrap_erpnext_test_fixtures()
		doc = _real_quote(3)
		self.assertEqual(doc.custom_vellox_approval_status, "Approved")
		self.assertEqual(doc.custom_vellox_approved_by, "auto")
		gate_submission(doc)  # no raise
