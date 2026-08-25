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


STAGE_PROBABILITY = {
	"Prospecting": 10,
	"Qualified": 30,
	"Proposal Sent": 60,
	"Negotiation": 80,
}

LOST_REASONS = ["Price", "Delay in implementation", "Chose a competitor", "Project postponed"]

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


def setup_opportunity_pipeline() -> None:
	"""Stages with approved probabilities + standard lost reasons."""
	from vellox_agency.setup.commercial import setup_commercial_foundation

	setup_commercial_foundation()  # guarantees UOM/company-independent masters
	_ensure_sales_stage_prospecting()
	if not frappe.db.exists("Opportunity Type", "Sales"):
		frappe.get_doc({"doctype": "Opportunity Type", "__newname": "Sales", "opportunity_type": "Sales"}).insert(
			ignore_permissions=True
		)

	for stage in STAGE_PROBABILITY:
		if not frappe.db.exists("Sales Stage", stage):
			frappe.get_doc({"doctype": "Sales Stage", "stage_name": stage}).insert(
				ignore_permissions=True
			)

	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
	create_custom_fields(
		{
			"Opportunity": [
				{
					"fieldname": "custom_vellox_probability",
					"label": "Vellox Probability (%)",
					"fieldtype": "Percent",
					"insert_after": "sales_stage",
				}
			],
			"Sales Stage": [
				{
					"fieldname": "custom_vellox_probability",
					"label": "Probability (%)",
					"fieldtype": "Percent",
					"insert_after": "stage_name",
				}
			],
		},
		update=True,
	)
	for stage, prob in STAGE_PROBABILITY.items():
		frappe.db.set_value("Sales Stage", stage, "custom_vellox_probability", prob)

	for reason in LOST_REASONS:
		if not frappe.db.exists("Opportunity Lost Reason", reason):
			frappe.get_doc(
				{"doctype": "Opportunity Lost Reason", "lost_reason": reason}
			).insert(ignore_permissions=True)
	frappe.db.commit()


QUOTATION_ESTIMATE_FIELDS = [
	{
		"fieldname": "custom_vellox_estimate_hours",
		"label": "Estimate Hours (role/hours/rate JSON)",
		"fieldtype": "Small Text",
		"insert_after": "custom_vellox_technical_proposal",
	},
	{
		"fieldname": "custom_vellox_vendor_cost",
		"label": "Vendor Cost (company currency)",
		"fieldtype": "Currency",
		"insert_after": "custom_vellox_estimate_hours",
	},
	{
		"fieldname": "custom_vellox_estimated_margin",
		"label": "Estimated Margin %",
		"fieldtype": "Percent",
		"insert_after": "custom_vellox_vendor_cost",
		"read_only": 1,
	},
]


def setup_quotation_estimate_fields() -> None:
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields({"Quotation": QUOTATION_ESTIMATE_FIELDS}, update=True)


def _ensure_uom() -> None:
	pass


def stamp_first_response_due(doc, method=None) -> None:
	from frappe.utils import add_to_date, now_datetime

	if doc.doctype == "Lead" and not doc.custom_vellox_first_response_due:
		doc.custom_vellox_first_response_due = add_to_date(now_datetime(), hours=FIRST_RESPONSE_HOURS)
