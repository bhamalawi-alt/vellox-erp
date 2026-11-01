"""Delivery roles, rate types and keeping money with Finance ([P4-31], plan sections 2 and 7).

- Every role named in the practice templates' steps is a Designation (on the
  Employee) and an Activity Type (on timesheet rows). Finance sets each
  person's rates in Activity Cost; the Activity Type's rates are the default.
- Money on projects, tasks, timesheets and rate types moves above the
  permission levels Project Managers, Operations and team members read, so
  they see hours and percentages but no amounts. ERPNext's accounting roles
  (held by the Finance and Agency Manager jobs) read them. Like
  grant_finance_export, this sets up Custom DocPerm for these doctypes.
"""

import frappe

from vellox_agency.setup.practice_templates import PRACTICE_TEMPLATES

MONEY_ROLES = ("Accounts User", "Accounts Manager")

# doctype -> (permlevel, fields). Project uses level 2 because ERPNext's level 1
# there (the Users table) is readable by every desk user. Timesheet Detail
# follows its parent's levels, where ERPNext already gives Accounts User level 1.
MONEY_FIELDS = {
	"Project": (
		2,
		(
			"estimated_costing",
			"total_costing_amount",
			"total_purchase_cost",
			"total_sales_amount",
			"total_billable_amount",
			"total_billed_amount",
			"total_consumed_material_cost",
			"gross_margin",
		),
	),
	"Task": (1, ("total_costing_amount", "total_billing_amount", "total_expense_claim")),
	"Timesheet": (
		1,
		("total_costing_amount", "total_billable_amount", "total_billed_amount", "base_total_costing_amount", "base_total_billable_amount", "base_total_billed_amount"),
	),
	"Timesheet Detail": (
		1,
		("costing_rate", "costing_amount", "billing_rate", "billing_amount", "base_costing_rate", "base_costing_amount", "base_billing_rate", "base_billing_amount"),
	),
	"Activity Type": (1, ("costing_rate", "billing_rate")),
}
WRITABLE_BY_MONEY_ROLES = {"Activity Type"}  # Finance sets the default rates


def delivery_roles() -> list[str]:
	return sorted({step[4] for steps in PRACTICE_TEMPLATES.values() for step in steps})


def setup_delivery_roles() -> None:
	for role in delivery_roles():
		if not frappe.db.exists("Designation", role):
			frappe.get_doc({"doctype": "Designation", "designation_name": role}).insert(ignore_permissions=True)
		if not frappe.db.exists("Activity Type", role):
			frappe.get_doc({"doctype": "Activity Type", "activity_type": role}).insert(ignore_permissions=True)
	hide_money_fields()


def hide_money_fields() -> None:
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter
	from frappe.permissions import add_permission, setup_custom_perms, update_permission_property

	for doctype, (level, fields) in MONEY_FIELDS.items():
		meta = frappe.get_meta(doctype)
		for fieldname in fields:
			field = meta.get_field(fieldname)
			if field and field.permlevel != level:
				make_property_setter(doctype, fieldname, "permlevel", level, "Int", validate_fields_for_doctype=False)
		if meta.istable:
			continue
		for role in MONEY_ROLES:
			filters = {"parent": doctype, "role": role, "permlevel": level, "if_owner": 0}
			if frappe.db.get_value("Custom DocPerm", filters, "read"):
				continue
			setup_custom_perms(doctype)
			if not frappe.db.exists("Custom DocPerm", filters):
				add_permission(doctype, role, level)
			update_permission_property(doctype, role, level, "read", 1, validate=False)
			if doctype in WRITABLE_BY_MONEY_ROLES:
				update_permission_property(doctype, role, level, "write", 1, validate=False)
		frappe.clear_cache(doctype=doctype)
