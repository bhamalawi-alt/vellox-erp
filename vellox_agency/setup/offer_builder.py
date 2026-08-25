from copy import deepcopy

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


OFFER_BUILDER_CUSTOM_FIELDS = {
	"Item": [
		{
			"fieldname": "custom_vellox_technical_proposal",
			"label": "Technical Proposal Template",
			"fieldtype": "Text Editor",
			"insert_after": "description",
			"depends_on": "eval:doc.is_stock_item == 0",
		},
		{
			"fieldname": "custom_vellox_default_duration",
			"label": "Default Duration",
			"fieldtype": "Data",
			"insert_after": "custom_vellox_technical_proposal",
			"depends_on": "eval:doc.is_stock_item == 0",
		},
		{
			"fieldname": "custom_vellox_billing_method",
			"label": "Billing Method",
			"fieldtype": "Select",
			"options": "Fixed Price\nMilestone\nRetainer\nTime and Materials",
			"insert_after": "custom_vellox_default_duration",
			"depends_on": "eval:doc.is_stock_item == 0",
		},
		{
			"fieldname": "custom_vellox_project_template",
			"label": "Project Template",
			"fieldtype": "Link",
			"options": "Project Template",
			"insert_after": "custom_vellox_billing_method",
			"depends_on": "eval:doc.is_stock_item == 0",
		},
	],
	"Quotation": [
		{
			"fieldname": "custom_vellox_technical_proposal",
			"label": "Technical Proposal",
			"fieldtype": "Text Editor",
			"insert_after": "terms",
		},
		{
			"fieldname": "custom_vellox_proposal_item_signature",
			"label": "Proposal Item Signature",
			"fieldtype": "Small Text",
			"insert_after": "custom_vellox_technical_proposal",
			"hidden": 1,
			"read_only": 1,
			"no_copy": 1,
		},
	],
}


def get_offer_builder_custom_fields():
	return deepcopy(OFFER_BUILDER_CUSTOM_FIELDS)


def setup_offer_builder():
	create_custom_fields(get_offer_builder_custom_fields(), update=True)
