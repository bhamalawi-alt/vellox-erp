"""Project phase follows its tasks (delivery plan section 2, [P3-99])."""

import frappe

from vellox_agency.crm_setup import PROJECT_PHASES

DONE_STATUSES = ("Completed", "Cancelled")


def phase_from_tasks(tasks: list[dict]) -> str | None:
	"""The earliest phase that still has open work; Post-Launch once all is done.

	None when no task carries a phase, so a typed phase is left alone.
	"""
	phased = [t for t in tasks if t["custom_vellox_phase"] in PROJECT_PHASES]
	if not phased:
		return None
	open_phases = [t["custom_vellox_phase"] for t in phased if t["status"] not in DONE_STATUSES]
	if not open_phases:
		return "Post-Launch"
	return min(open_phases, key=PROJECT_PHASES.index)


def update_project_phase(project: str) -> None:
	tasks = frappe.get_all(
		"Task", filters={"project": project}, fields=["custom_vellox_phase", "status"]
	)
	phase = phase_from_tasks(tasks)
	if not phase or frappe.db.get_value("Project", project, "custom_vellox_phase") == phase:
		return
	# A full save (not db_set) so the change lands in the Project's history.
	# Phase moves are rare, so this runs a few times per project.
	doc = frappe.get_doc("Project", project)
	doc.custom_vellox_phase = phase
	doc.save(ignore_permissions=True)


def sync_project_phase(doc, method=None) -> None:
	"""Task on_update / after_delete hook."""
	projects = {doc.project}
	before = doc.get_doc_before_save() if method == "on_update" else None
	if before:
		projects.add(before.project)  # a task moved out of a project
	for project in projects - {None, ""}:
		if frappe.db.exists("Project", project):
			update_project_phase(project)
