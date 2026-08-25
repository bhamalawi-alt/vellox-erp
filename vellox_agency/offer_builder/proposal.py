import json
from html import escape

import frappe
from frappe import _
from frappe.utils import cint, sanitize_html


def _unique_item_codes(item_codes):
	return list(dict.fromkeys(code for code in item_codes if code))


def get_item_signature(item_codes):
	return json.dumps(_unique_item_codes(item_codes), ensure_ascii=False, separators=(",", ":"))


def compose_technical_proposal(item_codes):
	sections = []
	skipped_items = []
	unique_codes = _unique_item_codes(item_codes)

	for item_code in unique_codes:
		item = frappe.get_doc("Item", item_code)
		item.check_permission("read")
		template = item.custom_vellox_technical_proposal or ""
		if not template.strip():
			skipped_items.append(item.item_name)
			continue

		metadata = []
		if item.custom_vellox_default_duration:
			metadata.append(
				f'<span><strong>{escape(_("Duration"))}:</strong> '
				f'{escape(item.custom_vellox_default_duration)}</span>'
			)
		if item.custom_vellox_billing_method:
			metadata.append(
				f'<span><strong>{escape(_("Billing Method"))}:</strong> '
				f'{escape(item.custom_vellox_billing_method)}</span>'
			)

		metadata_html = ""
		if metadata:
			metadata_html = f'<div class="vellox-service-meta">{" &middot; ".join(metadata)}</div>'

		sections.append(
			'<section class="vellox-service-proposal">'
			f"<h2>{escape(item.item_name)}</h2>"
			f"{metadata_html}"
			f'<div class="vellox-service-body">{sanitize_html(template, linkify=True)}</div>'
			"</section>"
		)

	if not sections:
		frappe.throw(_("No selected service has a Technical Proposal Template."))

	return {
		"html": "".join(sections),
		"item_signature": get_item_signature(unique_codes),
		"skipped_items": skipped_items,
	}


def _check_quotation_permission(quotation):
	if cint(quotation.get("docstatus")) != 0:
		frappe.throw(_("Technical proposals can only be generated for a draft Quotation."))

	name = quotation.get("name")
	if name and not str(name).startswith("new-") and frappe.db.exists("Quotation", name):
		stored = frappe.get_doc("Quotation", name)
		stored.check_permission("write")
		if stored.docstatus != 0:
			frappe.throw(_("Technical proposals can only be generated for a draft Quotation."))
		return

	if not frappe.has_permission("Quotation", "create"):
		frappe.throw(_("You are not permitted to create a Quotation."), frappe.PermissionError)


@frappe.whitelist()
def build_technical_proposal(quotation):
	quotation = frappe.parse_json(quotation)
	if quotation.get("doctype") != "Quotation":
		frappe.throw(_("A Quotation is required."))

	_check_quotation_permission(quotation)
	return compose_technical_proposal(
		[row.get("item_code") for row in quotation.get("items") or []]
	)
