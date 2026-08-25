"""Lead custom fields for the website intake flow (design section 2/3)."""

import frappe

LEAD_CUSTOM_FIELDS = {
	"Lead": [
		{
			"fieldname": "custom_vellox_services",
			"label": "Requested Services",
			"fieldtype": "Small Text",
			"insert_after": "request_type",
		},
		{
			"fieldname": "custom_vellox_inquiry",
			"label": "Inquiry Message",
			"fieldtype": "Long Text",
			"insert_after": "custom_vellox_services",
		},
		{
			"fieldname": "custom_vellox_first_response_due",
			"label": "First Response Due",
			"fieldtype": "Datetime",
			"insert_after": "custom_vellox_consent",
		},
		{
			"fieldname": "custom_vellox_qualified",
			"label": "Qualified",
			"fieldtype": "Check",
			"insert_after": "custom_vellox_first_response_due",
		},
		{
			"fieldname": "custom_vellox_consent",
			"label": "Contact Consent",
			"fieldtype": "Check",
			"insert_after": "custom_vellox_services",
		},
		{
			"fieldname": "custom_vellox_source_url",
			"label": "Source URL",
			"fieldtype": "Data",
			"insert_after": "custom_vellox_consent",
		},
	]
}


def setup_crm_intake_fields() -> None:
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(LEAD_CUSTOM_FIELDS, update=True)


ASSIGNMENT_RULE = "Vellox Intake Assignment"
FIRST_RESPONSE_HOURS = 4


def setup_lead_assignment_and_sla() -> None:
	_ensure_sales_stage_prospecting()
	if not frappe.db.exists("Assignment Rule", ASSIGNMENT_RULE):
		frappe.get_doc(
			{
				"doctype": "Assignment Rule",
				"name": ASSIGNMENT_RULE,
				"title": ASSIGNMENT_RULE,
				"document_type": "Lead",
				"description": "Round-robin new website inquiries among Vellox Sales users.",
				"assign_condition": 'status == "Lead"',
				"priority": 1,
				"users": [{"user": "Administrator"}],  # ops adds the real sales roster
				"assignment_days": [
					{"day": day}
					for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
				],
			}
		).insert(ignore_permissions=True)


def _ensure_sales_stage_prospecting() -> None:
	if not frappe.db.exists("Sales Stage", "Prospecting"):
		frappe.get_doc({"doctype": "Sales Stage", "stage_name": "Prospecting"}).insert(
			ignore_permissions=True
		)


def _ensure_uom() -> None:
	pass


def stamp_first_response_due(doc, method=None) -> None:
	from frappe.utils import add_to_date, now_datetime

	if doc.doctype == "Lead" and not doc.custom_vellox_first_response_due:
		doc.custom_vellox_first_response_due = add_to_date(now_datetime(), hours=FIRST_RESPONSE_HOURS)
