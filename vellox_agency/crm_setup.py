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
