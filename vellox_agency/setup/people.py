"""Staff fields for capacity planning ([P4-30], capacity plan section 2).

Employees and freelancers are both Frappe HR Employees; freelancers use the
Employment Type "Contract" that Frappe HR ships.
"""

import frappe

SENIORITY = ("Junior", "Mid", "Senior")
DEFAULT_DAILY_HOURS = 8
DEFAULT_UTILIZATION_TARGET = 75

EMPLOYEE_FIELDS = [
	{
		"fieldname": "custom_vellox_capacity_section",
		"label": "Capacity",
		"fieldtype": "Section Break",
		"insert_after": "holiday_list",
		"collapsible": 1,
	},
	{
		"fieldname": "custom_vellox_daily_hours",
		"label": "Daily Hours",
		"fieldtype": "Float",
		"default": str(DEFAULT_DAILY_HOURS),
		"non_negative": 1,
		"description": "Hours this person works on a working day.",
		"insert_after": "custom_vellox_capacity_section",
	},
	{
		"fieldname": "custom_vellox_utilization_target",
		"label": "Utilization Target",
		"fieldtype": "Percent",
		"default": str(DEFAULT_UTILIZATION_TARGET),
		"non_negative": 1,
		"description": "Share of available hours expected on client work.",
		"insert_after": "custom_vellox_daily_hours",
	},
	{
		"fieldname": "custom_vellox_seniority",
		"label": "Seniority",
		"fieldtype": "Select",
		"options": "\n" + "\n".join(SENIORITY),
		"insert_after": "custom_vellox_utilization_target",
	},
]


def setup_people_fields() -> None:
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields({"Employee": EMPLOYEE_FIELDS}, update=True)
	# Frappe HR creates it on install; make sure freelancers always have it.
	if not frappe.db.exists("Employment Type", "Contract"):
		frappe.get_doc({"doctype": "Employment Type", "employee_type_name": "Contract"}).insert(ignore_permissions=True)


def validate_capacity_fields(doc, method=None) -> None:
	"""Employee validate: a utilization target is a share of available hours."""
	target = doc.get("custom_vellox_utilization_target")
	if target is not None and not 0 <= target <= 100:
		frappe.throw(
			frappe._("Utilization Target must be between 0 and 100 (got {0}).").format(target),
			frappe.ValidationError,
		)
