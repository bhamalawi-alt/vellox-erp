import frappe
from frappe.tests.utils import FrappeTestCase

from vellox_agency.acceptance import _ensure_acceptance_fields, create_project_from_quotation
from vellox_agency.crm_setup import setup_quotation_estimate_fields
from vellox_agency.setup.commercial import setup_commercial_foundation


class TestAcceptanceMapper(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.tests.test_offer_builder import (
			_bootstrap_erpnext_test_fixtures,
			TEST_CUSTOMER,
			TEST_PRICE_LIST,
		)

		cls.TEST_CUSTOMER = TEST_CUSTOMER
		cls.TEST_PRICE_LIST = TEST_PRICE_LIST
		_bootstrap_erpnext_test_fixtures()
		setup_commercial_foundation()
		setup_quotation_estimate_fields()
		_ensure_acceptance_fields()

	def _submitted_quotation_with_template(self):
		from erpnext.selling.doctype.quotation.test_quotation import make_quotation

		if not frappe.db.exists("Project Template", "Vellox Delivery Template"):
			# ERPNext v15 (15.124+) only accepts template tasks in a Project Template.
			seed_task = frappe.new_doc("Task")
			seed_task.subject = "Kickoff"
			seed_task.is_template = 1
			seed_task.insert(ignore_permissions=True)
			tpl = frappe.new_doc("Project Template")
			tpl.template_name = "Vellox Delivery Template"
			tpl.name = "Vellox Delivery Template"
			tpl.append("tasks", {"task": seed_task.name, "subject": "Kickoff"})
			tpl.insert(ignore_permissions=True)
		item = "_Test Vellox Iso Service"
		if not frappe.db.exists("Item", item):
			from erpnext.stock.doctype.item.test_item import make_item

			make_item(item, {"is_stock_item": 0, "stock_uom": "Unit"})
		frappe.db.set_value("Item", item, "custom_vellox_project_template", "Vellox Delivery Template")

		q = make_quotation(
			item=item,
			party_name=self.TEST_CUSTOMER,
			selling_price_list=self.TEST_PRICE_LIST,
			warehouse="",
			qty=1,
			rate=100000,
			do_not_submit=False,
		)
		return q

	def test_creates_project_from_submitted_quotation(self):
		q = self._submitted_quotation_with_template()
		res = create_project_from_quotation(q.name)
		project = frappe.get_doc("Project", res["project"])
		self.assertEqual(project.custom_vellox_quotation, q.name)
		self.assertEqual(project.customer, self.TEST_CUSTOMER)
		tasks = frappe.get_all(
			"Task",
			filters={"project": project.name},
			fields=["subject"],
		)
		self.assertTrue(
			any(t["subject"].startswith("_Test Vellox Iso Service: Kickoff") for t in tasks),
			f"template task not created: {tasks}",
		)

	def test_mapper_is_idempotent(self):
		q = self._submitted_quotation_with_template()
		first = create_project_from_quotation(q.name)
		second = create_project_from_quotation(q.name)
		self.assertEqual(first["project"], second["project"])
		self.assertTrue(second["existing"])

	def test_practice_service_creates_its_steps_as_tasks(self):
		from erpnext.selling.doctype.quotation.test_quotation import make_quotation

		from vellox_agency.setup.commercial import PRACTICES
		from vellox_agency.setup.practice_templates import (
			PRACTICE_TEMPLATES,
			get_steps,
			setup_practice_templates,
		)

		setup_practice_templates()
		item_code = PRACTICES[0]["item_code"]
		template = next(iter(PRACTICE_TEMPLATES))
		self.assertEqual(frappe.db.get_value("Item", item_code, "custom_vellox_project_template"), template)
		steps = get_steps(template)
		item_name = frappe.db.get_value("Item", item_code, "item_name")

		q = make_quotation(
			item=item_code,
			party_name=self.TEST_CUSTOMER,
			selling_price_list=self.TEST_PRICE_LIST,
			warehouse="",
			qty=1,
			rate=100000,
			do_not_submit=False,
		)
		project = create_project_from_quotation(q.name)["project"]

		tasks = frappe.get_all(
			"Task",
			filters={"project": project},
			fields=["name", "subject", "is_milestone", "custom_vellox_default_role"],
			order_by="creation asc",
		)
		self.assertEqual([t.subject for t in tasks], [f"{item_name}: {s.subject}"[:140] for s in steps])
		self.assertEqual([t.is_milestone for t in tasks], [s.is_milestone for s in steps])
		self.assertEqual([t.custom_vellox_default_role for t in tasks], [s.default_role for s in steps])
		for step, task in zip(steps, tasks, strict=True):
			depends_on = frappe.get_all("Task Depends On", filters={"parent": task.name}, pluck="task")
			expected = [tasks[step.depends_on_step - 1].name] if step.depends_on_step else []
			self.assertEqual(depends_on, expected, step.subject)

	def test_draft_quotation_is_rejected(self):
		q = self._submitted_quotation_with_template()
		draft = frappe.copy_doc(q)
		draft.docstatus = 0
		draft.custom_vellox_project = None
		draft.insert(ignore_permissions=True)
		with self.assertRaisesRegex(frappe.ValidationError, "submitted"):
			create_project_from_quotation(draft.name)
