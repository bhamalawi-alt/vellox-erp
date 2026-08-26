import frappe
from frappe.tests.utils import FrappeTestCase

from vellox_agency.crm_setup import setup_project_health_field


def _cr(**kw):
	doc = {"doctype": "Vellox Change Request", "title": "Scope bump", **kw}
	return frappe.get_doc(doc)


class TestHealthAndChangeRequests(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.tests.test_offer_builder import (
			_bootstrap_erpnext_test_fixtures,
		)

		_bootstrap_erpnext_test_fixtures()
		setup_project_health_field()
		frappe.reload_doctype("Vellox Change Request")

		cls.project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": "_Test CR Project",
				"company": "_Test Company",
				"expected_end_date": frappe.utils.nowdate(),
			}
		).insert(ignore_permissions=True)

	def _fresh(self, name):
		return frappe.get_doc("Vellox Change Request", name)

	def _transition(self, name, status, **fields):
		doc = self._fresh(name)
		doc.status = status
		for key, value in fields.items():
			setattr(doc, key, value)
		doc.save()
		return doc

	def _submitted_amendment(self):
		from erpnext.selling.doctype.quotation.test_quotation import make_quotation
		from erpnext.stock.doctype.item.test_item import make_item
		from vellox_agency.tests.test_offer_builder import TEST_CUSTOMER, TEST_PRICE_LIST

		item = "_Test Vellox Iso Service"
		if not frappe.db.exists("Item", item):
			make_item(item, {"is_stock_item": 0, "stock_uom": "Unit"})

		return make_quotation(
			item=item,
			party_name=TEST_CUSTOMER,
			selling_price_list=TEST_PRICE_LIST,
			warehouse="",
			qty=1,
			rate=50000,
			do_not_submit=False,
		)

	def test_health_change_by_non_manager_is_denied(self):
		staff = "health-staff@example.com"
		if not frappe.db.exists("User", staff):
			u = frappe.get_doc(
				{"doctype": "User", "email": staff, "first_name": "Staff", "send_welcome_email": 0}
			)
			u.insert(ignore_permissions=True)
			u.add_roles("Agency Staff")
			u.save(ignore_permissions=True)
		with self.set_user(staff):
			project = frappe.get_doc("Project", self.project.name)
			project.custom_vellox_health = "At Risk"
			with self.assertRaises(frappe.PermissionError):
				project.save()

	def test_cr_lifecycle_happy_path_shifts_schedule(self):
		cr = _cr(project=self.project.name, schedule_impact_days=10, price_impact=0).insert(
			ignore_permissions=True
		)
		self._transition(cr.name, "Under Review")
		before = self.project.expected_end_date
		doc = self._transition(cr.name, "Approved")
		self.assertEqual(doc.approved_by, "Administrator")
		end_after = frappe.db.get_value("Project", self.project.name, "expected_end_date")
		from frappe.utils import add_days, get_datetime

		self.assertEqual(
			get_datetime(end_after).date(), get_datetime(add_days(before, 10)).date()
		)

	def test_price_cr_requires_submitted_amendment_before_implemented(self):
		cr = _cr(project=self.project.name, price_impact=25000).insert(ignore_permissions=True)
		self._transition(cr.name, "Under Review")
		self._transition(cr.name, "Approved")
		with self.assertRaisesRegex(frappe.ValidationError, "SUBMITTED"):
			self._transition(cr.name, "Implemented")
		amendment = self._submitted_amendment()
		self._transition(cr.name, "Implemented", amendment_quotation=amendment.name)

	def test_illegal_transition_rejected(self):
		cr = _cr(project=self.project.name).insert(ignore_permissions=True)
		with self.assertRaisesRegex(frappe.ValidationError, "Illegal transition"):
			self._transition(cr.name, "Implemented")
