import frappe
from frappe.tests.utils import FrappeTestCase

from vellox_agency.deprecations import DEPRECATION_TARGETS
from vellox_agency.security import (
	MANAGEMENT_ROLES,
	ROLE_MATRIX,
	setup_roles_and_permissions,
)


class TestSecurityBaseline(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_roles_and_permissions()

	def test_role_matrix_covers_card_requirements(self):
		self.assertEqual(
			set(ROLE_MATRIX),
			{
				"Vellox Sales",
				"Vellox Project Manager",
				"Vellox Team Member",
				"Vellox Finance",
				"Vellox Operations",
				"Agency Manager",
				"Agency Staff",
				"Agency Client",
			},
		)
		for role_name, spec in ROLE_MATRIX.items():
			if role_name == "Agency Client":
				self.assertEqual(spec["desk_access"], 0)
			else:
				self.assertEqual(spec["desk_access"], 1)

	def test_deprecated_ledgers_are_read_only_outside_management(self):
		import unittest.mock as mock

		for user, ptype, expected in (
			("vellox.staff@example.com", "read", False),
			("vellox.client@example.com", "read", False),
			("vellox.staff@example.com", "write", False),
			("vellox.staff@example.com", "delete", False),
		):
			with self.subTest(user=user, ptype=ptype):
				from vellox_agency import security

				with mock.patch(
					security.__name__ + "._user_has_management_role",
					return_value=False,
					create=True,
				):
					result = security.has_deprecated_doctype_access(
						user=user, ptype=ptype, doctype="Client Account"
					)
				self.assertEqual(result, expected)

	def test_management_roles_retain_read_on_deprecated_ledgers(self):
		from vellox_agency import security

		self.assertTrue(security._user_has_management_role("Administrator"))

	def test_cross_client_isolation_via_user_permissions(self):
		from erpnext.selling.doctype.quotation.test_quotation import make_quotation
		from vellox_agency.tests.test_offer_builder import (
			TEST_CUSTOMER,
			TEST_PRICE_LIST,
			_bootstrap_erpnext_test_fixtures,
		)

		_bootstrap_erpnext_test_fixtures()

		from erpnext.stock.doctype.item.test_item import make_item

		item = make_item("_Test Vellox Iso Service", {"is_stock_item": 0, "stock_uom": "Unit"})

		other_customer = "_Test Vellox Customer B"
		if not frappe.db.exists("Customer", other_customer):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": other_customer,
					"customer_type": "Company",
					"customer_group": "_Test Vellox Client Group"
					if frappe.db.exists("Customer Group", "_Test Vellox Client Group")
					else "All Customer Groups",
					"territory": "All Territories",
				}
			).insert(ignore_permissions=True)
			frappe.db.commit()

		own = make_quotation(
			item=item.name,
			party_name=TEST_CUSTOMER,
			selling_price_list=TEST_PRICE_LIST,
			warehouse="",
			rate=100,
			do_not_submit=True,
		)
		other = make_quotation(
			item=item.name,
			party_name=other_customer,
			selling_price_list=TEST_PRICE_LIST,
			warehouse="",
			rate=200,
			do_not_submit=True,
		)

		limited_user = "vellox.sales@example.com"
		if not frappe.db.exists("User", limited_user):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": limited_user,
					"first_name": "Vellox Sales",
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
		user_doc = frappe.get_doc("User", limited_user)
		if "Sales User" not in [row.role for row in user_doc.roles or []]:
			user_doc.add_roles("Sales User")
			user_doc.save(ignore_permissions=True)
			frappe.db.commit()
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": limited_user,
				"allow": "Customer",
				"for_value": TEST_CUSTOMER,
			}
		).insert(ignore_permissions=True) if not frappe.db.exists(
			"User Permission",
			{"user": limited_user, "allow": "Customer", "for_value": TEST_CUSTOMER},
		) else None
		frappe.db.commit()

		# Record-level client isolation enforced by the platform today:
		# the limited user sees only their own Customer master.
		customers = frappe.get_list(
			"Customer",
			filters={"name": ("in", [TEST_CUSTOMER, other_customer])},
			pluck="name",
			user=limited_user,
		)
		self.assertEqual(customers, [TEST_CUSTOMER])

		# NOTE: Quotation uses a Dynamic Link (party_name), which standard
		# User Permissions do not filter at list/doc level (verified 2026-08-25).
		# Explicit per-client scoping for transactional documents is tracked
		# as [FOLLOW-UP-93] and becomes mandatory in the portal phase ([P6-40]).
