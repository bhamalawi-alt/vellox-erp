"""Close the last API routes that showed hidden money ([P4-34]).

1. Filters. Frappe v15 refuses sorting or grouping on a field the caller
   cannot read, but not filtering, so repeated "cost > 5000?" lists could
   narrow a hidden amount down. Every whitelisted list, count, value, stats and
   search method is wrapped to refuse such filters (owner, 2026-11-01). The REST
   list and count routes call Frappe's functions directly, so after_request
   replaces their response with a refusal instead.
2. REST create and update (/api/resource POST and PUT, /api/v2/document POST)
   return the saved document without Frappe's field-level read filter. The
   after_request hook applies it, as REST read and the client_guard wrappers do.
3. A quote's estimate panel moves to its own permission level, read by Sales,
   Operations, Finance and the Agency Manager, not Project Managers.

Known limit: server-side code that calls frappe.get_list with filters it takes
from a user is not covered; the app has none.
"""

import json
import re

import frappe
from frappe import _
from frappe.model import get_permitted_fields

from vellox_agency.crm_setup import ESTIMATE_PERMLEVEL  # Quotation level 1 is ERPNext's own

ESTIMATE_READERS = ("Vellox Finance",)
ESTIMATE_WRITERS = ("Vellox Sales", "Vellox Operations", "Agency Manager", "System Manager")

REST_LISTS = (
	re.compile(r"^/api/(?:v1/)?resource/([^/]+)/?$"),
	re.compile(r"^/api/v2/document/([^/]+)/?$"),
	re.compile(r"^/api/v2/doctype/([^/]+)/count/?$"),
)
REST_WRITE = re.compile(r"^/api/(?:v1/)?resource/[^/]+(?:/.+)?$|^/api/v2/document/[^/]+(?:/.+)?$")


def setup_estimate_access() -> None:
	"""Who reads and writes the estimate fields, which crm_setup puts at ESTIMATE_PERMLEVEL."""
	from vellox_agency.security import grant_permlevel

	for role in ESTIMATE_READERS + ESTIMATE_WRITERS:
		grant_permlevel("Quotation", role, ESTIMATE_PERMLEVEL, "read")
	for role in ESTIMATE_WRITERS:
		grant_permlevel("Quotation", role, ESTIMATE_PERMLEVEL, "write")
	frappe.clear_cache(doctype="Quotation")


def refuse_hidden_filters(doctype: str, filters, parent_doctype: str | None = None) -> None:
	"""Raise PermissionError when `filters` use a field the session user cannot read."""
	if not filters or frappe.session.user == "Administrator":
		return
	if isinstance(filters, str):
		try:
			filters = json.loads(filters)
		except ValueError:
			return  # a document name
	if isinstance(filters, dict):
		filters = [{key: value} for key, value in filters.items()]
	if not isinstance(filters, list | tuple):
		return
	for f in filters:
		fieldname, filter_doctype = _filter_field(doctype, f)
		if fieldname and _hidden(filter_doctype, fieldname, parent_doctype or doctype):
			raise frappe.PermissionError(_("Not permitted to filter by {0}").format(frappe.bold(fieldname)))


def _filter_field(doctype: str, f) -> tuple[str | None, str]:
	if isinstance(f, dict):
		return (next(iter(f)), doctype) if f else (None, doctype)
	if isinstance(f, list | tuple):
		if len(f) >= 4:
			return f[1], f[0] or doctype
		if len(f) >= 2:
			return f[0], doctype
	return None, doctype


def _hidden(doctype: str, fieldname, parent_doctype: str) -> bool:
	if not isinstance(fieldname, str) or not frappe.db.exists("DocType", doctype):
		return False
	df = frappe.get_meta(doctype).get_field(fieldname.strip("`"))
	if not df or not df.permlevel:
		return False  # standard fields and level-0 fields are always readable
	parenttype = parent_doctype if parent_doctype != doctype else None
	return df.fieldname not in get_permitted_fields(
		doctype=doctype, parenttype=parenttype, permission_type="read"
	)


# Whitelisted methods (override_whitelisted_methods in hooks.py).


@frappe.whitelist()
def get_list(doctype, filters=None, or_filters=None, parent=None, **kwargs):
	from frappe import client

	refuse_hidden_filters(doctype, filters, parent)
	refuse_hidden_filters(doctype, or_filters, parent)
	return frappe.call(
		client.get_list, doctype, filters=filters, or_filters=or_filters, parent=parent, **kwargs
	)


@frappe.whitelist()
def get_count(doctype, filters=None, **kwargs):
	from frappe import client

	refuse_hidden_filters(doctype, filters)
	return frappe.call(client.get_count, doctype, filters=filters, **kwargs)


@frappe.whitelist()
def get_value(doctype, fieldname, filters=None, parent=None, **kwargs):
	from frappe import client

	refuse_hidden_filters(doctype, filters, parent)
	return frappe.call(client.get_value, doctype, fieldname, filters=filters, parent=parent, **kwargs)


def _refuse_form_dict_filters(doctype: str | None = None) -> None:
	form = frappe.local.form_dict
	doctype = doctype or form.get("doctype")
	if doctype:
		refuse_hidden_filters(doctype, form.get("filters"))
		refuse_hidden_filters(doctype, form.get("or_filters"))


@frappe.whitelist()
@frappe.read_only()
def reportview_get():
	from frappe.desk import reportview

	_refuse_form_dict_filters()
	return reportview.get()


@frappe.whitelist()
@frappe.read_only()
def reportview_get_list():
	from frappe.desk import reportview

	_refuse_form_dict_filters()
	return reportview.get_list()


@frappe.whitelist()
@frappe.read_only()
def reportview_get_count():
	from frappe.desk import reportview

	_refuse_form_dict_filters()
	return reportview.get_count()


@frappe.whitelist()
@frappe.read_only()
def get_sidebar_stats(stats, doctype, filters=None):
	from frappe.desk import reportview

	refuse_hidden_filters(doctype, filters)
	return reportview.get_sidebar_stats(stats, doctype, filters)


@frappe.whitelist()
def get_group_by_count(doctype, current_filters, field):
	from frappe.desk import listview

	refuse_hidden_filters(doctype, current_filters)
	return listview.get_group_by_count(doctype, current_filters, field)


@frappe.whitelist()
def search_link(doctype, txt, filters=None, **kwargs):
	from frappe.desk import search

	refuse_hidden_filters(doctype, filters)
	return frappe.call(search.search_link, doctype, txt, filters=filters, **kwargs)


@frappe.whitelist()
def search_widget(doctype, txt, filters=None, **kwargs):
	from frappe.desk import search

	refuse_hidden_filters(doctype, filters)
	return frappe.call(search.search_widget, doctype, txt, filters=filters, **kwargs)


# REST routes, which call Frappe's functions directly.


def after_request(response, request) -> None:
	"""after_request hook: refuse hidden filters on REST lists; filter REST write responses."""
	user = frappe.session.user if getattr(frappe.local, "session", None) else "Guest"
	if user in ("Administrator", "Guest") or response.status_code != 200:
		return
	path = request.path
	if request.method == "GET":
		for pattern in REST_LISTS:
			if match := pattern.match(path):
				_refuse_rest_list(response, match.group(1))
				return
	elif request.method in ("POST", "PUT", "PATCH") and REST_WRITE.match(path):
		_filter_rest_document(response)


def _refuse_rest_list(response, doctype: str) -> None:
	try:
		_refuse_form_dict_filters(doctype)
	except frappe.PermissionError as error:
		frappe.local.message_log = []
		response.status_code = 403
		response.set_data(json.dumps({"exc_type": "PermissionError", "exception": str(error)}))


def _filter_rest_document(response) -> None:
	from frappe.utils.response import json_handler

	from vellox_agency.client_guard import _readable

	try:
		body = json.loads(response.get_data())
	except ValueError:
		return
	data = body.get("data") if isinstance(body, dict) else None
	if not isinstance(data, dict) or not data.get("doctype"):
		return
	body["data"] = _readable(data)
	response.set_data(json.dumps(body, default=json_handler))
