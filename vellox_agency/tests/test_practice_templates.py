import frappe
from frappe.tests.utils import FrappeTestCase

from vellox_agency.setup.practice_templates import (
	PRACTICE_TEMPLATES,
	get_steps,
	setup_practice_templates,
)


class TestPracticeTemplates(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.tests.test_offer_builder import (
			_bootstrap_erpnext_test_fixtures,
		)

		_bootstrap_erpnext_test_fixtures()
		setup_practice_templates()

	def test_seven_templates_exist_with_ordered_steps(self):
		self.assertEqual(len(PRACTICE_TEMPLATES), 7)
		for template_name, steps in PRACTICE_TEMPLATES.items():
			self.assertTrue(frappe.db.exists("Project Template", template_name))
			rows = get_steps(template_name)
			self.assertEqual(len(rows), len(steps), template_name)
			self.assertEqual(rows[0]["subject"], steps[0][0])

	def test_catalogue_items_link_to_their_template(self):
		from vellox_agency.setup.commercial import PRACTICES

		for index, practice in enumerate(PRACTICES):
			template_name = list(PRACTICE_TEMPLATES)[index]
			self.assertEqual(
				frappe.db.get_value("Item", practice["item_code"], "custom_vellox_project_template"),
				template_name,
			)

	def test_steps_form_valid_dependency_chain(self):
		for template_name in PRACTICE_TEMPLATES:
			rows = get_steps(template_name)
			for position, row in enumerate(rows, start=1):
				dep = row["depends_on_step"]
				if dep:
					self.assertLess(dep, position, f"{template_name} step {position} dependency")
					self.assertTrue(rows[dep - 1]["subject"], "dependency target exists")

	def test_template_edits_never_mutate_created_projects(self):
		from vellox_agency.acceptance import create_project_from_template

		template_name = list(PRACTICE_TEMPLATES)[0]
		res = create_project_from_template(template_name)
		project = frappe.get_doc("Project", res["project"])
		tasks_before = sorted(t.subject for t in frappe.get_all("Task", filters={"project": project.name}, fields=["subject"]))

		# mutate the TEMPLATE after project creation
		tpl = frappe.get_doc("Project Template", template_name)
		tpl.set("custom_vellox_steps", [{"subject": "Mutated step", "phase": "Discovery", "is_milestone": 0, "depends_on_step": 0, "default_role": "", "est_days": 1}])
		tpl.flags.ignore_permissions = True
		tpl.flags.ignore_mandatory = True
		frappe.flags.in_patch = True
		tpl.save()

		tasks_after = sorted(t.subject for t in frappe.get_all("Task", filters={"project": project.name}, fields=["subject"]))
		self.assertEqual(tasks_before, tasks_after)
