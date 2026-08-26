"""Acceptance mapper: submitted Quotation -> ERPNext Project (design §6)."""

import frappe
from frappe import _
from frappe.utils import nowdate

CREATION_ROLES = ("System Manager", "Agency Manager", "Vellox Project Manager")


def _ensure_acceptance_fields() -> None:
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(
		{
			"Quotation": [
				{
					"fieldname": "custom_vellox_project",
					"label": "Linked Project",
					"fieldtype": "Link",
					"options": "Project",
					"read_only": 1,
					"insert_after": "custom_vellox_approved_by",
					"no_copy": 1,
				}
			],
			"Project": [
				{
					"fieldname": "custom_vellox_quotation",
					"label": "Source Quotation",
					"fieldtype": "Link",
					"options": "Quotation",
					"read_only": 1,
					"insert_after": "expected_start_date",
					"no_copy": 1,
				},
				{
					"fieldname": "custom_vellox_expected_margin_percent",
					"label": "Expected Margin % (frozen)",
					"fieldtype": "Percent",
					"read_only": 1,
					"insert_after": "custom_vellox_quotation",
				},
			],
		},
		update=True,
	)


@frappe.whitelist()
def create_project_from_quotation(quotation: str):
	_ensure_acceptance_fields()

	doc = frappe.get_doc("Quotation", quotation)
	doc.check_permission("read")

	if not set(CREATION_ROLES) & set(frappe.get_roles()):
		frappe.throw(_("Not permitted to create Projects."), frappe.PermissionError)

	if doc.docstatus != 1:
		frappe.throw(_("Only a submitted Quotation can create a Project."))

	if doc.custom_vellox_project and frappe.db.exists("Project", doc.custom_vellox_project):
		return {"ok": True, "project": doc.custom_vellox_project, "existing": True}

	customer = doc.party_name if doc.quotation_to == "Customer" else None

	project = frappe.new_doc("Project")
	project.project_name = f"{doc.name} {doc.customer_name or ''}".strip()
	project.company = doc.company
	if customer and frappe.db.exists("Customer", customer):
		project.customer = customer
	project.expected_start_date = nowdate()
	project.custom_vellox_quotation = doc.name
	project.custom_vellox_expected_margin_percent = doc.get(
		"custom_vellox_estimated_margin"
	)
	project.insert(ignore_permissions=True)
	_create_template_tasks(doc, project)

	doc.db_set("custom_vellox_project", project.name)
	return {"ok": True, "project": project.name, "existing": False}


def _create_template_tasks(doc, project) -> int:
	created = 0
	for row in doc.items or []:
		template = frappe.db.get_value("Item", row.item_code, "custom_vellox_project_template")
		if not template:
			continue
		tpl = frappe.get_doc("Project Template", template)
		for task_row in tpl.tasks or []:
			subject = f"{row.item_name}: {task_row.subject}"
			task = frappe.new_doc("Task")
			task.subject = subject[:140]
			task.project = project.name
			task.insert(ignore_permissions=True)
			created += 1
	return created
