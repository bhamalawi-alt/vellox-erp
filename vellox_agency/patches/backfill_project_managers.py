"""Give projects created before [P3-99] a Project Manager: their creator.

New projects get one on insert; without this, older projects would send their
client-review and "project created" alerts to nobody.
"""

import frappe


def execute():
	project = frappe.qb.DocType("Project")
	(
		frappe.qb.update(project)
		.set(project.custom_vellox_project_manager, project.owner)
		.where(project.custom_vellox_project_manager.isnull() | (project.custom_vellox_project_manager == ""))
		.run()
	)
