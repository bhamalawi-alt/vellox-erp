"""Stop the upgrade if the prototype Skill DocTypes still hold records ([P4-102]).

[P4-102] removes the app's prototype Skill and Skill Employee DocTypes so Frappe
HR can own Skill; migrate then deletes them as orphans. That is only safe when
they are empty: their rows would otherwise be left in unused tables, with no
warning. Runs before the model sync, and again on every migrate until it passes.
"""

import frappe
from frappe import _


def _rows(doctype: str) -> int:
	if not frappe.db.table_exists(doctype):
		return 0
	return frappe.db.sql(f"select count(*) from `tab{doctype}`")[0][0]


def execute():
	skill_is_ours = frappe.db.get_value("DocType", "Skill", "module") == "Vellox Agency HR"
	stranded = _rows("Skill Employee") + (_rows("Skill") if skill_is_ours else 0)
	if stranded:
		frappe.throw(
			_(
				"This site has {0} record(s) in the old Vellox Skill / Skill Employee DocTypes, "
				"which this version removes in favour of Frappe HR's Skill and Employee Skill Map. "
				"Move or export them first, then migrate again."
			).format(stranded),
			frappe.ValidationError,
		)
