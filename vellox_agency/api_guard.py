"""Keep hidden money out of API answers ([P4-34]).

Frappe v15 strips hidden fields from records it returns, but does not check
what a request asks with, so a Project Manager could still learn a hidden
amount by:

1. Filtering on it ("cost > 5000?" again and again). Frappe refuses sorting
   and grouping on hidden fields, not filtering (owner, 2026-11-01: refuse).
2. Naming it inside a formula in the requested fields
   ("percent_complete + total_costing_amount"): Frappe checks only the first
   name in an expression.
3. Using routes that send back a whole document: REST create and update, and
   document methods (run_doc_method).

The checks read filters the way Frappe does (a field the doctype lacks is
looked up on its child tables) and match field names in any letter case.
Whitelisted methods are wrapped in override_whitelisted_methods; the REST
list and count routes call Frappe directly, so after_request refuses those
answers instead, and withholds any answer it fails to check.
unreviewed_filtering_methods() lists every whitelisted method in frappe,
erpnext and hrms that takes filters or field names and could reach a Vellox
money doctype without being wrapped or reviewed; a test keeps it empty, so a
new upstream method fails CI rather than leaking.

4. A quote's estimate panel moves to its own permission level, read by Sales,
   Operations, Finance and the Agency Manager, not Project Managers, and is
   not printed.

Known limit: server-side code that passes a user's filters straight to
frappe.get_list is not covered; the app has none. ERPNext's own permission
levels on other doctypes (orders, invoices) are left as ERPNext set them.
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
	"""Raise PermissionError when `filters` use a field the session user cannot read.

	Each filter is read as Frappe reads it (frappe.utils.get_filter), so a field
	the doctype lacks but a child table has is checked on that child table.
	"""
	from frappe.utils import get_filter

	filters = _parsed(filters)
	if not filters or _exempt():
		return
	if isinstance(filters, dict):
		filters = [{key: value} for key, value in filters.items()]
	if not isinstance(filters, list | tuple):
		return  # a document name
	for item in filters:
		if not isinstance(item, dict | list | tuple):
			continue
		f = get_filter(doctype, item)
		if _hidden(f.doctype, f.fieldname, parent_doctype or doctype):
			raise frappe.PermissionError(_("Not permitted to filter by {0}").format(frappe.bold(f.fieldname)))


def refuse_hidden_fields(
	doctype: str, fields, parent_doctype: str | None = None, only_formulas: bool = False
) -> None:
	"""Raise PermissionError when `fields` read a hidden field, also inside a formula.

	Frappe strips a hidden column from list results only when it is the first
	name in the expression, so "percent_complete + total_costing_amount" would
	return it. With only_formulas (list queries), a lone hidden column is left
	for Frappe to strip, so saved list and report layouts keep working.
	"""
	from frappe.desk.reportview import extract_fieldnames

	fields = _parsed(fields)
	if not fields or _exempt():
		return
	for field in fields if isinstance(fields, list | tuple) else [fields]:
		if isinstance(field, dict):  # {child table field: [columns]}
			for table_field, columns in field.items():
				df = frappe.get_meta(doctype).get_field(table_field)
				if df and df.options:
					refuse_hidden_fields(df.options, columns, doctype, only_formulas)
			continue
		if not isinstance(field, str):
			continue
		columns = extract_fieldnames(field)
		if only_formulas and len(columns) <= 1:
			continue
		for column in columns:
			if not isinstance(column, str) or column == "*":
				continue
			column_doctype, fieldname = doctype, column.replace("`", "")
			if "." in fieldname:
				table, fieldname = fieldname.split(".", 1)
				column_doctype = table.removeprefix("tab")
			if _hidden(column_doctype, fieldname, parent_doctype or doctype):
				raise frappe.PermissionError(_("Not permitted to read {0}").format(frappe.bold(fieldname)))


def refuse_hidden_query(
	doctype, filters=None, or_filters=None, fields=None, parent=None, only_formulas: bool = True
) -> None:
	"""Filters and requested columns of a list query (see refuse_hidden_fields)."""
	refuse_hidden_filters(doctype, filters, parent)
	refuse_hidden_filters(doctype, or_filters, parent)
	refuse_hidden_fields(doctype, fields, parent, only_formulas)


def _exempt() -> bool:
	return frappe.session.user == "Administrator"


def _parsed(value):
	if isinstance(value, str):
		try:
			return json.loads(value)
		except ValueError:
			return value  # a name, or a single field expression
	return value


def _hidden(doctype, fieldname, parent_doctype) -> bool:
	"""A real field of `doctype`, in any letter case, above level 0 and not readable."""
	if not isinstance(doctype, str) or not isinstance(fieldname, str):
		return False
	try:
		meta = frappe.get_meta(doctype)
	except frappe.DoesNotExistError:
		return False
	wanted = fieldname.strip().lower()
	df = next((d for d in meta.fields if d.fieldname.lower() == wanted), None)
	if not df or not df.permlevel:
		return False  # standard fields and level-0 fields are always readable
	parenttype = parent_doctype if parent_doctype and parent_doctype != doctype else None
	return df.fieldname not in get_permitted_fields(
		doctype=doctype, parenttype=parenttype, permission_type="read"
	)


# Whitelisted methods (override_whitelisted_methods in hooks.py).


@frappe.whitelist()
def get_list(doctype, fields=None, filters=None, or_filters=None, parent=None, **kwargs):
	from frappe import client

	refuse_hidden_query(doctype, filters, or_filters, fields, parent)
	return frappe.call(
		client.get_list,
		doctype,
		fields=fields,
		filters=filters,
		or_filters=or_filters,
		parent=parent,
		**kwargs,
	)


@frappe.whitelist()
def get_count(doctype, filters=None, **kwargs):
	from frappe import client

	refuse_hidden_filters(doctype, filters)
	return frappe.call(client.get_count, doctype, filters=filters, **kwargs)


@frappe.whitelist()
def get_value(doctype, fieldname, filters=None, parent=None, **kwargs):
	from frappe import client

	refuse_hidden_query(doctype, filters, fields=fieldname, parent=parent)
	return frappe.call(client.get_value, doctype, fieldname, filters=filters, parent=parent, **kwargs)


@frappe.whitelist()
def get(doctype, name=None, filters=None, parent=None):
	from frappe import client

	refuse_hidden_filters(doctype, filters, parent)
	return client.get(doctype, name=name, filters=filters, parent=parent)


def _refuse_form_dict_filters(doctype: str | None = None) -> None:
	form = frappe.local.form_dict
	doctype = doctype or form.get("doctype")
	if doctype:
		parent = form.get("parent") or form.get("parenttype") or form.get("parent_doctype")
		refuse_hidden_query(doctype, form.get("filters"), form.get("or_filters"), form.get("fields"), parent)


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
@frappe.read_only()
def get_stats(stats, doctype, filters=None):
	from frappe.desk import reportview

	refuse_hidden_filters(doctype, filters)
	return reportview.get_stats(stats, doctype, filters)


@frappe.whitelist()
@frappe.read_only()
def get_filter_dashboard_data(stats, doctype, filters=None):
	from frappe.desk import reportview

	refuse_hidden_filters(doctype, filters)
	return reportview.get_filter_dashboard_data(stats, doctype, filters)


@frappe.whitelist()
def get_next(doctype, value, prev, filters=None, sort_order="desc", sort_field="modified"):
	from frappe.desk.form import utils

	refuse_hidden_filters(doctype, filters)
	refuse_hidden_fields(doctype, [sort_field])
	return utils.get_next(doctype, value, prev, filters, sort_order, sort_field)


@frappe.whitelist()
def get_calendar_events(doctype, start, end, field_map, filters=None, fields=None):
	from frappe.desk import calendar

	refuse_hidden_query(doctype, filters, fields=fields)
	mapped = _parsed(field_map)
	if isinstance(mapped, dict):
		refuse_hidden_fields(doctype, [v for v in mapped.values() if isinstance(v, str)])
	return calendar.get_events(doctype, start, end, field_map, filters, fields)


@frappe.whitelist()
def get_timesheet_events(start, end, filters=None):
	from erpnext.projects.doctype.timesheet import timesheet

	refuse_hidden_filters("Timesheet", filters)
	return timesheet.get_events(start, end, filters)


@frappe.whitelist()
def get_number_card_result(doc, filters, to_date=None):
	from frappe.desk.doctype.number_card import number_card

	card = frappe._dict(_parsed(doc) or {})
	_refuse_card(
		card.document_type, filters, card.get("filters_json"), [card.get("aggregate_function_based_on")]
	)
	return number_card.get_result(doc, filters, to_date)


@frappe.whitelist()
def get_number_card_difference(doc, filters, result):
	from frappe.desk.doctype.number_card import number_card

	card = frappe._dict(_parsed(doc) or {})
	if card.get("name") and frappe.db.exists("Number Card", card.name):
		card = frappe.get_cached_doc("Number Card", card.name)
	_refuse_card(
		card.get("document_type"),
		filters,
		card.get("filters_json"),
		[card.get("aggregate_function_based_on")],
	)
	return number_card.get_percentage_difference(doc, filters, result)


@frappe.whitelist()
def get_dashboard_chart(chart_name=None, chart=None, filters=None, **kwargs):
	from frappe.desk.doctype.dashboard_chart import dashboard_chart

	if chart_name and frappe.db.exists("Dashboard Chart", chart_name):
		spec = frappe.get_cached_doc("Dashboard Chart", chart_name).as_dict()
	else:
		spec = frappe._dict(_parsed(chart) or {})
	columns = [
		spec.get(key)
		for key in ("value_based_on", "based_on", "group_by_based_on", "aggregate_function_based_on")
	]
	_refuse_card(spec.get("document_type"), filters, spec.get("filters_json"), columns)
	return frappe.call(dashboard_chart.get, chart_name=chart_name, chart=chart, filters=filters, **kwargs)


def _refuse_card(doctype, filters, saved_filters, columns) -> None:
	if not doctype:
		return
	refuse_hidden_filters(doctype, filters)
	refuse_hidden_filters(doctype, saved_filters)
	refuse_hidden_fields(doctype, [c for c in columns if isinstance(c, str) and c])


@frappe.whitelist()
def run_doc_method(method, docs=None, dt=None, dn=None, arg=None, args=None):
	"""Document methods send the document back; send only the fields the caller may read."""
	from frappe import handler

	try:
		return handler.run_doc_method(method, docs=docs, dt=dt, dn=dn, arg=arg, args=args)
	finally:
		for doc in frappe.response.get("docs") or []:
			if hasattr(doc, "apply_fieldlevel_read_permissions"):
				doc.apply_fieldlevel_read_permissions()


@frappe.whitelist()
def validate_link(doctype, docname, fields=None):
	from frappe import client

	refuse_hidden_fields(doctype, fields, only_formulas=True)
	return client.validate_link(doctype, docname, fields)


@frappe.whitelist()
def get_coords(doctype, filters, type):
	from frappe.geo import utils

	refuse_hidden_filters(doctype, filters)
	return utils.get_coords(doctype, filters, type)


@frappe.whitelist()
def get_monthly_goal_graph_data(
	title,
	doctype,
	docname,
	goal_value_field,
	goal_total_field,
	goal_history_field,
	goal_doctype,
	goal_doctype_link,
	goal_field,
	date_field,
	aggregation="sum",
	filters=None,
):
	from frappe.utils import goal

	refuse_hidden_fields(doctype, [goal_value_field, goal_total_field, goal_history_field])
	# The goal total is summed outside list permissions, so any hidden column is refused.
	refuse_hidden_query(
		goal_doctype, filters, fields=[goal_field, date_field, goal_doctype_link], only_formulas=False
	)
	return goal.get_monthly_goal_graph_data(
		title,
		doctype,
		docname,
		goal_value_field,
		goal_total_field,
		goal_history_field,
		goal_doctype,
		goal_doctype_link,
		goal_field,
		date_field,
		aggregation,
		filters,
	)


@frappe.whitelist(allow_guest=True)
def get_list_data(
	doctype, txt=None, limit_start=0, fields=None, cmd=None, limit=20, web_form_name=None, **kwargs
):
	"""Portal lists: extra parameters become filters on fields of the same name."""
	from frappe.www import list as portal_list

	refuse_hidden_fields(doctype, fields, only_formulas=True)
	refuse_hidden_filters(doctype, {key: value for key, value in kwargs.items() if not key.startswith("_")})
	return portal_list.get_list_data(
		doctype,
		txt=txt,
		limit_start=limit_start,
		fields=fields,
		limit=limit,
		web_form_name=web_form_name,
		**kwargs,
	)


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
	"""after_request hook: refuse hidden filters on REST lists; filter REST write responses.

	Frappe logs and ignores errors raised here and sends the response anyway, so
	any failure replaces the body with a refusal rather than letting it through.
	"""
	if response.status_code != 200 or not getattr(frappe.local, "session", None) or _exempt():
		return
	path = request.path
	try:
		if request.method == "GET":
			for pattern in REST_LISTS:
				if match := pattern.match(path):
					_refuse_form_dict_filters(match.group(1))
					return
		elif request.method in ("POST", "PUT", "PATCH") and REST_WRITE.match(path):
			_filter_rest_document(response)
	except frappe.PermissionError as error:
		_replace(response, 403, "PermissionError", str(error))
	except Exception:
		frappe.log_error(title=_("Vellox API guard failed; response withheld"))
		_replace(response, 500, "ValidationError", _("The response could not be checked and was withheld."))


def _replace(response, status: int, exc_type: str, message: str) -> None:
	frappe.local.message_log = []
	response.status_code = status
	response.set_data(json.dumps({"exc_type": exc_type, "exception": message}))


def _filter_rest_document(response) -> None:
	from frappe.utils.response import json_handler

	body = json.loads(response.get_data())
	data = body.get("data") if isinstance(body, dict) else None
	if not isinstance(data, dict) or not data.get("doctype"):
		return
	body["data"] = _readable_body(data)
	response.set_data(json.dumps(body, default=json_handler))


def _readable_body(data: dict) -> dict:
	from vellox_agency.client_guard import _readable

	return _readable(data)


def unreviewed_filtering_methods() -> list[str]:
	"""Whitelisted methods in frappe, erpnext and hrms that take filters or field names,
	could reach a doctype with Vellox-hidden fields, and are neither wrapped here nor
	reviewed in REVIEWED_METHODS. A new upstream method then fails CI instead of leaking."""
	import ast
	import os

	overrides = frappe.get_hooks("override_whitelisted_methods") or {}
	found = []
	for app in ("frappe", "erpnext", "hrms"):
		root = frappe.get_app_path(app)
		for folder, _dirs, files in os.walk(root):
			if f"{os.sep}tests" in folder or f"{os.sep}patches" in folder:
				continue
			for filename in files:
				if not filename.endswith(".py") or filename.startswith("test_"):
					continue
				path = os.path.join(folder, filename)
				with open(path, encoding="utf-8") as handle:
					source = handle.read()
				if "whitelist" not in source:
					continue
				try:
					tree = ast.parse(source)
				except SyntaxError:
					continue
				module = f"{app}." + os.path.relpath(path[:-3], root).replace(os.sep, ".")
				module = module.removesuffix(".__init__")
				for node in tree.body:
					if not isinstance(node, ast.FunctionDef):
						continue
					if not any("whitelist" in ast.unparse(d) for d in node.decorator_list):
						continue
					params = {a.arg for a in node.args.args + node.args.kwonlyargs}
					if not params & QUERY_PARAMS:
						continue
					body = ast.get_source_segment(source, node) or ""
					names_money = any(f'"{dt}"' in body or f"'{dt}'" in body for dt in MONEY_DOCTYPES)
					# Link-search queries take `doctype` but read their own fixed table.
					search_query = {"txt", "searchfield", "page_len"} <= params
					caller_picks_doctype = bool(params & {"doctype", "doc", "chart"}) and not search_query
					if not (names_money or caller_picks_doctype):
						continue
					name = f"{module}.{node.name}"
					if name not in overrides and name not in REVIEWED_METHODS:
						found.append(name)
	return sorted(found)


# Doctypes whose fields Vellox hides from some jobs ([P4-31], [P4-33], [P4-34]).
MONEY_DOCTYPES = (
	"Project",
	"Task",
	"Timesheet",
	"Timesheet Detail",
	"Activity Type",
	"Activity Cost",
	"Quotation",
)
QUERY_PARAMS = {"filters", "or_filters", "current_filters", "fields", "fieldname", "sort_field", "order_by"}
_FIXED_TABLE = "reads its own fixed tables, none with Vellox-hidden fields"
REVIEWED_METHODS: dict[str, str] = {
	"erpnext.accounts.dashboard_chart_source.account_balance_timeline.account_balance_timeline.get": _FIXED_TABLE,
	"erpnext.stock.dashboard_chart_source.warehouse_wise_stock_value.warehouse_wise_stock_value.get": _FIXED_TABLE,
	"erpnext.stock.doctype.pick_list.pick_list.get_pending_work_orders": _FIXED_TABLE,
	"hrms.hr.dashboard_chart_source.employees_by_age.employees_by_age.get_data": _FIXED_TABLE,
	"hrms.hr.dashboard_chart_source.hiring_vs_attrition_count.hiring_vs_attrition_count.get_data": _FIXED_TABLE,
	"erpnext.controllers.queries.get_project_name": "Project search; reads only the customer and company filter keys",
	"erpnext.projects.doctype.timesheet.timesheet.get_timesheet": "Timesheet search; reads only the project filter key",
	"erpnext.projects.utils.query_task": "Task search; ignores filters",
	"frappe.client.get_password": "returns only Password fields, after Frappe's own write-permission check",
	"frappe.core.doctype.access_log.access_log.make_access_log": "stores the filters in a log; queries nothing",
	"frappe.custom.doctype.customize_form.customize_form.get_link_filters_from_doc_without_customisations": (
		"reads DocType metadata, not records"
	),
}
