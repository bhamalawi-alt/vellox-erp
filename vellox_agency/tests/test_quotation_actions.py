"""Approve / Create Project buttons on the Quotation form ([P3-98])."""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from vellox_agency.crm_setup import setup_commercial_approval_fields
from vellox_agency.security import JOB_PROFILES, setup_roles_and_permissions


def _quote(discount=0, margin=50.0, status="Pending", docstatus=0, project=None):
	gross = 100000
	return frappe._dict(
		doctype="Quotation",
		name="_Test Actions Quote",
		docstatus=docstatus,
		net_total=round(gross * (1 - discount / 100.0), 2),
		items=[frappe._dict(amount=gross)],
		custom_vellox_estimated_margin=margin,
		custom_vellox_approval_status=status,
		custom_vellox_project=project,
	)


OPS_TIER = {"discount": 10, "margin": 30.0}
MANAGER_TIER = {"discount": 30, "margin": 10.0}


class _JobUsersCase(FrappeTestCase):
	"""One user per job, created once per class (user creation is throttled)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.tests.test_offer_builder import _bootstrap_erpnext_test_fixtures

		_bootstrap_erpnext_test_fixtures()
		setup_commercial_approval_fields()
		setup_roles_and_permissions()
		tag = frappe.generate_hash(length=8)
		cls.users = {}
		for job in ("Sales", "Operations", "Agency Manager", "Project Manager"):
			email = f"actions-{job.lower().replace(' ', '-')}-{tag}@example.com"
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Actions", "send_welcome_email": 0}).insert(
				ignore_permissions=True
			)
			frappe.get_doc("User", email).add_roles(*JOB_PROFILES[job])
			cls.users[job] = email


class TestQuotationActions(_JobUsersCase):
	def _actions(self, job, quote):
		from vellox_agency.approval import quotation_actions

		with self.set_user(self.users[job]):
			return quotation_actions(quote)

	def test_operations_approves_only_its_own_tier(self):
		from vellox_agency.approval import can_approve

		with self.set_user(self.users["Operations"]):
			self.assertTrue(can_approve(_quote(**OPS_TIER)))
			self.assertFalse(can_approve(_quote(**MANAGER_TIER)))
		with self.set_user(self.users["Agency Manager"]):
			self.assertTrue(can_approve(_quote(**MANAGER_TIER)))
		with self.set_user(self.users["Sales"]):
			self.assertFalse(can_approve(_quote(**OPS_TIER)))

	def test_approve_button_follows_the_approval_rules(self):
		cases = [
			("Operations", _quote(**OPS_TIER), True),
			("Operations", _quote(**MANAGER_TIER), False),
			("Agency Manager", _quote(**MANAGER_TIER), True),
			("Sales", _quote(**OPS_TIER), False),
			("Agency Manager", _quote(**MANAGER_TIER, status="Approved"), False),
			("Agency Manager", _quote(), False),  # auto-approved band needs no approval
			("Agency Manager", _quote(**MANAGER_TIER, docstatus=1), False),
		]
		for job, quote, expected in cases:
			with self.subTest(job=job, quote=dict(quote)):
				self.assertEqual(self._actions(job, quote)["can_approve"], expected)

	def test_create_project_button_only_for_submitted_quotes_without_a_project(self):
		cases = [
			("Project Manager", _quote(docstatus=1), True),
			("Agency Manager", _quote(docstatus=1), True),
			("Sales", _quote(docstatus=1), False),
			("Project Manager", _quote(docstatus=0), False),
		]
		for job, quote, expected in cases:
			with self.subTest(job=job, docstatus=quote.docstatus):
				self.assertEqual(self._actions(job, quote)["can_create_project"], expected)

	def test_linked_project_is_offered_instead_of_creating_another(self):
		project = frappe.get_doc(
			{"doctype": "Project", "project_name": f"_Test Actions {frappe.generate_hash(length=6)}", "company": "_Test Company"}
		).insert(ignore_permissions=True)
		actions = self._actions("Project Manager", _quote(docstatus=1, project=project.name))
		self.assertFalse(actions["can_create_project"])
		self.assertEqual(actions["project"], project.name)

	def test_state_changing_actions_accept_only_post(self):
		from vellox_agency.acceptance import create_project_from_quotation
		from vellox_agency.approval import approve_quotation

		for fn in (approve_quotation, create_project_from_quotation):
			with self.subTest(fn=fn.__name__):
				self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func.get(fn), ["POST"])

	def test_quotation_form_receives_the_actions_on_load(self):
		from erpnext.selling.doctype.quotation.test_quotation import make_quotation
		from erpnext.stock.doctype.item.test_item import make_item

		from vellox_agency.tests.test_offer_builder import TEST_CUSTOMER, TEST_PRICE_LIST

		item = "_Test Vellox Actions Service"
		if not frappe.db.exists("Item", item):
			make_item(item, {"is_stock_item": 0, "stock_uom": "Unit"})
		quote = make_quotation(
			item=item, party_name=TEST_CUSTOMER, selling_price_list=TEST_PRICE_LIST, warehouse="", qty=1, rate=100,
			do_not_save=True,
		)
		quote.insert(ignore_permissions=True)
		with self.set_user(self.users["Agency Manager"]):
			doc = frappe.get_doc("Quotation", quote.name)
			doc.run_method("onload")
			# 0% discount and no estimate costs: the auto band, nothing to approve.
			self.assertEqual(
				doc.get_onload().get("vellox_actions"),
				{"can_approve": False, "can_create_project": False, "project": None},
			)


def _real_quote(discount, labor_cost=0):
	"""A saved draft quote of 1000 with `discount`% off and `labor_cost` estimated."""
	from erpnext.selling.doctype.quotation.test_quotation import make_quotation
	from erpnext.stock.doctype.item.test_item import make_item

	from vellox_agency.tests.test_offer_builder import TEST_CUSTOMER, TEST_PRICE_LIST

	item = "_Test Vellox Actions Service"
	if not frappe.db.exists("Item", item):
		make_item(item, {"is_stock_item": 0, "stock_uom": "Unit"})
	quote = make_quotation(
		item=item, party_name=TEST_CUSTOMER, selling_price_list=TEST_PRICE_LIST, warehouse="", qty=1, rate=1000,
		do_not_save=True,
	)
	quote.apply_discount_on = "Net Total"
	quote.additional_discount_percentage = discount
	if labor_cost:
		quote.custom_vellox_estimate_hours = json.dumps([{"role": "Dev", "hours": 1, "rate": labor_cost}])
	return quote.insert(ignore_permissions=True)


def _ops_tier_quote():
	return _real_quote(10, labor_cost=630)  # 10% off, 30% margin


def _manager_tier_quote():
	return _real_quote(30, labor_cost=630)  # 30% off, 10% margin


class TestApprovalGate(_JobUsersCase):
	"""Only approve_quotation can approve, and a material change re-opens approval."""

	def _approval(self, name):
		return frappe.db.get_value(
			"Quotation", name, ["custom_vellox_approval_status", "custom_vellox_approved_by"], as_dict=True
		)

	def _approve(self, job, name):
		from vellox_agency.approval import approve_quotation

		with self.set_user(self.users[job]):
			return approve_quotation(name)

	def test_editing_the_approval_fields_does_not_approve(self):
		quote = _manager_tier_quote()
		with self.set_user(self.users["Sales"]):
			doc = frappe.get_doc("Quotation", quote.name)
			doc.custom_vellox_approval_status = "Approved"
			doc.custom_vellox_approved_by = self.users["Agency Manager"]
			doc.save()
			self.assertEqual(self._approval(quote.name).custom_vellox_approval_status, "Pending")
			self.assertFalse(self._approval(quote.name).custom_vellox_approved_by)
			with self.assertRaisesRegex(frappe.ValidationError, "commercial approval"):
				frappe.get_doc("Quotation", quote.name).submit()

	def test_new_and_copied_quotes_start_unapproved(self):
		quote = _manager_tier_quote()
		self._approve("Agency Manager", quote.name)
		copy = frappe.copy_doc(frappe.get_doc("Quotation", quote.name)).insert(ignore_permissions=True)
		self.assertEqual(copy.custom_vellox_approval_status, "Pending")
		self.assertFalse(copy.custom_vellox_approved_by)

	def test_approver_must_match_the_tier(self):
		quote = _manager_tier_quote()
		with self.assertRaises(frappe.PermissionError):
			self._approve("Operations", quote.name)
		self._approve("Agency Manager", quote.name)
		approval = self._approval(quote.name)
		self.assertEqual(approval.custom_vellox_approval_status, "Approved")
		self.assertEqual(approval.custom_vellox_approved_by, self.users["Agency Manager"])

		ops_quote = _ops_tier_quote()
		self._approve("Operations", ops_quote.name)
		self.assertEqual(self._approval(ops_quote.name).custom_vellox_approved_by, self.users["Operations"])

	def test_an_approval_is_not_overwritten(self):
		quote = _ops_tier_quote()
		self._approve("Agency Manager", quote.name)
		with self.assertRaisesRegex(frappe.ValidationError, "already approved"):
			self._approve("Operations", quote.name)
		self.assertEqual(self._approval(quote.name).custom_vellox_approved_by, self.users["Agency Manager"])

	def test_only_drafts_can_be_approved(self):
		quote = _ops_tier_quote()
		self._approve("Operations", quote.name)
		frappe.get_doc("Quotation", quote.name).submit()
		with self.assertRaisesRegex(frappe.ValidationError, "draft"):
			self._approve("Agency Manager", quote.name)

	def test_a_material_change_reopens_approval(self):
		quote = _ops_tier_quote()
		self._approve("Operations", quote.name)
		doc = frappe.get_doc("Quotation", quote.name)
		doc.additional_discount_percentage = 30
		doc.save(ignore_permissions=True)
		self.assertEqual(self._approval(quote.name).custom_vellox_approval_status, "Pending")
		self.assertFalse(self._approval(quote.name).custom_vellox_approved_by)
		with self.assertRaisesRegex(frappe.ValidationError, "commercial approval"):
			frappe.get_doc("Quotation", quote.name).submit()

	def test_an_unchanged_resave_keeps_approval(self):
		quote = _ops_tier_quote()
		self._approve("Operations", quote.name)
		doc = frappe.get_doc("Quotation", quote.name)
		doc.terms = "Payment within 30 days."
		doc.save(ignore_permissions=True)
		self.assertEqual(self._approval(quote.name).custom_vellox_approval_status, "Approved")

	def test_leaving_the_auto_band_reopens_approval(self):
		quote = _real_quote(0)
		self.assertEqual(self._approval(quote.name).custom_vellox_approved_by, "auto")
		doc = frappe.get_doc("Quotation", quote.name)
		doc.additional_discount_percentage = 30
		doc.save(ignore_permissions=True)
		self.assertEqual(self._approval(quote.name).custom_vellox_approval_status, "Pending")
