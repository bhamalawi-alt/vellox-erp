"""Seven Vellox practice delivery templates ([P3-24]).

Each published practice gets an idempotently-managed ERPNext Project
Template whose ordered steps (phase / milestone / dependency / role /
duration) live on a Vellox-owned child table so dependencies and
milestones survive into real Projects as a valid Task graph.
"""

import frappe

STEPS_DOCTYPE = "Vellox Practice Step"

# (subject, phase, is_milestone, depends_on_step_1based, default_role, est_days)
PRACTICE_TEMPLATES = {
	"Vellox — Brand Strategy": [
		("Discovery workshop & brief", "Discovery", 0, 0, "Project Manager", 3),
		("Market & audience research", "Discovery", 0, 1, "Strategist", 8),
		("Positioning platform draft", "Design", 0, 2, "Strategist", 6),
		("Strategy document v1 (Milestone)", "Design", 1, 3, "Strategist", 4),
		("Client walkthrough & sign-off", "Design", 1, 4, "Project Manager", 3),
	],
	"Vellox — Brand Identity": [
		("Creative territory exploration", "Design", 0, 0, "Art Director", 10),
		("Logo & system refinement", "Design", 0, 1, "Designer", 12),
		("Brand book assembly", "Build", 0, 2, "Designer", 8),
		("Identity package handover (Milestone)", "Launch", 1, 3, "Art Director", 4),
	],
	"Vellox — User Experience Design": [
		("User research & interviews", "Discovery", 0, 0, "UX Researcher", 10),
		("Information architecture", "Design", 0, 1, "UX Designer", 6),
		("High-fidelity screens", "Design", 0, 2, "UI Designer", 20),
		("Prototype & usability test (Milestone)", "Build", 1, 3, "UX Designer", 6),
		("Engineering handoff pack (Milestone)", "Launch", 1, 4, "UX Designer", 4),
	],
	"Vellox — Visual Content": [
		("Pre-production planning", "Discovery", 0, 0, "Producer", 5),
		("Shoot execution", "Build", 0, 1, "Producer", 5),
		("Post-production edits", "Build", 0, 2, "Editor", 10),
		("Multi-format asset delivery (Milestone)", "Launch", 1, 3, "Editor", 5),
	],
	"Vellox — Web Development": [
		("Technical architecture", "Discovery", 0, 0, "Tech Lead", 4),
		("Weekly incremental builds", "Build", 0, 1, "Developer", 30),
		("QA & performance pass", "Build", 0, 2, "QA Engineer", 8),
		("Launch checklist go-live (Milestone)", "Launch", 1, 3, "Tech Lead", 3),
	],
	"Vellox — eCommerce": [
		("Platform architecture & migration plan", "Discovery", 0, 0, "Tech Lead", 6),
		("Storefront build & integrations", "Build", 0, 1, "Developer", 30),
		("Catalogue & checkout QA", "Build", 0, 2, "QA Engineer", 8),
		("Go-live & CRO baseline (Milestone)", "Launch", 1, 3, "Tech Lead", 4),
	],
	"Vellox — Web and Mobile Applications": [
		("Product strategy & scope", "Discovery", 0, 0, "Product Manager", 6),
		("Sprint zero foundation", "Build", 0, 1, "Tech Lead", 8),
		("Feature sprints", "Build", 0, 2, "Developer", 40),
		("Store submission / release (Milestone)", "Launch", 1, 3, "Tech Lead", 6),
	],
}


def _ensure_step_child_doctype() -> None:
	frappe.reload_doctype(STEPS_DOCTYPE, force=True)


def setup_practice_templates() -> None:
	_ensure_step_child_doctype()
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(
		{
			"Project Template": [
				{
					"fieldname": "custom_vellox_steps",
					"label": "Practice Steps",
					"fieldtype": "Table",
					"options": STEPS_DOCTYPE,
					"insert_after": "tasks",
				}
			]
		},
		update=True,
	)
	for template_name, steps in PRACTICE_TEMPLATES.items():
		if frappe.db.exists("Project Template", template_name):
			tpl = frappe.get_doc("Project Template", template_name)
		else:
			tpl = frappe.new_doc("Project Template")
			tpl.template_name = template_name
			tpl.name = template_name
		tpl.set(
			"custom_vellox_steps",
			[
				{
					"subject": subject,
					"phase": phase,
					"is_milestone": milestone,
					"depends_on_step": depends_on,
					"default_role": role,
					"est_days": days,
				}
				for subject, phase, milestone, depends_on, role, days in steps
			],
		)
		tpl.flags.ignore_permissions = True
		# standard tasks grid is intentionally unused; steps carry the plan
		tpl.flags.ignore_mandatory = True
		frappe.flags.in_patch = True
		try:
			tpl.save()
		finally:
			frappe.flags.in_patch = False
	# link catalogue items to their practice template
	from vellox_agency.setup.commercial import PRACTICES

	for index, practice in enumerate(PRACTICES):
		template_name = list(PRACTICE_TEMPLATES)[index] if index < len(PRACTICE_TEMPLATES) else None
		if template_name:
			frappe.db.set_value(
				"Item", practice["item_code"], "custom_vellox_project_template", template_name
			)
	frappe.db.commit()


def get_steps(template_name: str) -> list[dict]:
	rows = frappe.get_all(
		STEPS_DOCTYPE,
		filters={"parent": template_name, "parenttype": "Project Template"},
		fields=["subject", "phase", "is_milestone", "depends_on_step", "default_role", "est_days", "idx"],
		order_by="idx asc",
	)
	return rows
