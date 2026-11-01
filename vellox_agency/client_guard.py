"""frappe.client write calls return only fields the caller may read ([P4-31]).

frappe.client.set_value / insert / save / submit / cancel return the whole
saved document without Frappe's field-level read filter, so a Project Manager
saving a project through them would receive its hidden cost and margin
amounts. These wrappers apply the filter the desk form and frappe.client.get
already apply.

The REST routes (/api/resource create and update, /api/v2/document create)
get the same filter in api_guard.after_request ([P4-34]).
"""

import frappe
from frappe import client


def _readable(result):
	if not isinstance(result, dict) or not result.get("doctype"):
		return result
	doc = frappe.get_doc(result)
	doc.apply_fieldlevel_read_permissions()
	return doc.as_dict()


@frappe.whitelist(methods=["POST", "PUT"])
def set_value(doctype, name, fieldname, value=None):
	return _readable(client.set_value(doctype, name, fieldname, value))


@frappe.whitelist(methods=["POST", "PUT"])
def insert(doc=None):
	return _readable(client.insert(doc))


@frappe.whitelist(methods=["POST", "PUT"])
def save(doc):
	return _readable(client.save(doc))


@frappe.whitelist(methods=["POST", "PUT"])
def submit(doc):
	return _readable(client.submit(doc))


@frappe.whitelist(methods=["POST", "PUT"])
def cancel(doctype, name):
	return _readable(client.cancel(doctype, name))
