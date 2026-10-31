"""Approve / Create Project buttons on the Quotation form ([P3-98])."""

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


class TestQuotationActions(FrappeTestCase):
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
			self.assertIn("can_approve", doc.get_onload().get("vellox_actions", {}))
