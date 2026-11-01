"""The last API routes that showed hidden money ([P4-34]).

- Lists, counts, single values and searches refuse filters on fields the
  caller cannot read, so a hidden amount cannot be narrowed down by asking
  "cost > 5000?" again and again (owner, 2026-11-01).
- REST create and update (/api/resource, /api/v2/document) return only the
  fields the caller may read, like REST read already does.
- A quote's estimate panel (hours with rates, vendor cost, estimated margin) is
  hidden from Project Managers; Sales, Operations, Finance and the Agency
  Manager keep it (owner, 2026-11-01).
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from werkzeug.wrappers import Response

from vellox_agency.security import JOB_PROFILES

PM_USER = "ag-pm@example.com"
OPS_USER = "ag-operations@example.com"
FIN_USER = "ag-finance@example.com"
HIDDEN_COST = {"total_costing_amount": [">", 5000]}


def _user(email, roles):
	# Never Sales or Agency Manager roles (they join lead routing on the test site).
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "AG", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
		frappe.get_doc("User", email).add_roles(*roles)
	return email


class _GuardCase(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.security import setup_roles_and_permissions
		from vellox_agency.setup.roles_rates import setup_delivery_roles

		setup_delivery_roles()
		setup_roles_and_permissions()
		_user(PM_USER, JOB_PROFILES["Project Manager"])
		_user(OPS_USER, JOB_PROFILES["Operations"])
		_user(FIN_USER, JOB_PROFILES["Finance"])


class TestHiddenFilters(_GuardCase):
	def test_filters_on_hidden_fields_are_refused_in_every_shape(self):
		from vellox_agency.api_guard import refuse_hidden_filters

		shapes = [
			{"total_costing_amount": [">", 5000]},
			[["total_costing_amount", ">", 5000]],
			[["Project", "total_costing_amount", ">", 5000]],
			json.dumps([["Project", "total_costing_amount", ">", 5000]]),
		]
		with self.set_user(PM_USER):
			for filters in shapes:
				with self.subTest(filters=filters):
					with self.assertRaises(frappe.PermissionError):
						refuse_hidden_filters("Project", filters)
			refuse_hidden_filters("Project", {"status": "Open"})  # a readable field is fine
			refuse_hidden_filters("Project", "PROJ-0001")  # a name is fine
			refuse_hidden_filters("Project", None)

	def test_child_table_filters_are_checked_too(self):
		from vellox_agency.api_guard import refuse_hidden_filters

		with self.set_user(PM_USER):
			with self.assertRaises(frappe.PermissionError):
				refuse_hidden_filters("Timesheet", [["Timesheet Detail", "costing_amount", ">", 10]])
			refuse_hidden_filters("Timesheet", [["Timesheet Detail", "hours", ">", 1]])

	def test_people_who_may_read_the_field_may_filter_on_it(self):
		from vellox_agency.api_guard import refuse_hidden_filters

		with self.set_user(FIN_USER):
			refuse_hidden_filters("Project", HIDDEN_COST)

	def test_the_list_methods_refuse_them(self):
		from vellox_agency import api_guard

		calls = {
			"frappe.client.get_list": lambda: api_guard.get_list("Project", filters=HIDDEN_COST),
			"frappe.client.get_count": lambda: api_guard.get_count("Project", filters=HIDDEN_COST),
			"frappe.client.get_value": lambda: api_guard.get_value("Project", "name", filters=HIDDEN_COST),
			"frappe.desk.listview.get_group_by_count": lambda: api_guard.get_group_by_count(
				"Project", json.dumps(HIDDEN_COST), "status"
			),
			"frappe.desk.reportview.get_sidebar_stats": lambda: api_guard.get_sidebar_stats(
				json.dumps(["status"]), "Project", json.dumps(HIDDEN_COST)
			),
			"frappe.desk.search.search_link": lambda: api_guard.search_link(
				"Project", "", filters=HIDDEN_COST
			),
		}
		with self.set_user(PM_USER):
			for name, call in calls.items():
				with self.subTest(method=name):
					with self.assertRaises(frappe.PermissionError):
						call()

	def test_the_desk_list_view_refuses_them(self):
		from vellox_agency import api_guard

		for fn in (api_guard.reportview_get, api_guard.reportview_get_list, api_guard.reportview_get_count):
			with self.subTest(fn=fn.__name__), self.set_user(PM_USER):
				frappe.local.form_dict = frappe._dict(
					doctype="Project", fields=json.dumps(["name"]), filters=json.dumps(HIDDEN_COST)
				)
				with self.assertRaises(frappe.PermissionError):
					fn()

	def test_a_normal_list_still_works(self):
		from vellox_agency import api_guard

		with self.set_user(PM_USER):
			self.assertIsInstance(api_guard.get_list("Project", filters={"status": "Open"}), list)

	def test_the_methods_are_routed_through_the_guard(self):
		overrides = frappe.get_hooks("override_whitelisted_methods")
		for method in (
			"frappe.client.get_list",
			"frappe.client.get_count",
			"frappe.client.get_value",
			"frappe.desk.reportview.get",
			"frappe.desk.reportview.get_list",
			"frappe.desk.reportview.get_count",
			"frappe.desk.reportview.get_sidebar_stats",
			"frappe.desk.listview.get_group_by_count",
			"frappe.desk.search.search_link",
			"frappe.desk.search.search_widget",
		):
			with self.subTest(method=method):
				self.assertTrue(overrides.get(method, [""])[-1].startswith("vellox_agency.api_guard."))


def _rest(path, method, payload, form_dict=None):
	from vellox_agency.api_guard import after_request

	frappe.local.form_dict = frappe._dict(form_dict or {})
	response = Response(json.dumps(payload), status=200, mimetype="application/json")
	after_request(response=response, request=SimpleNamespace(path=path, method=method))
	return response


class TestRestRoutes(_GuardCase):
	def _project(self):
		project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"_Test AG {frappe.generate_hash(length=5)}",
				"company": "_Test Company",
			}
		).insert(ignore_permissions=True)
		return project.as_dict(convert_dates_to_str=True)

	def test_create_and_update_return_only_readable_fields(self):
		data = self._project()
		data["total_costing_amount"] = 5200
		with self.set_user(PM_USER):
			for path, method in (
				("/api/resource/Project", "POST"),
				(f"/api/resource/Project/{data['name']}", "PUT"),
				("/api/v1/resource/Project", "POST"),
				("/api/v2/document/Project", "POST"),
			):
				with self.subTest(path=path, method=method):
					body = json.loads(_rest(path, method, {"data": data}).get_data())
					self.assertFalse(body["data"]["total_costing_amount"])  # 0, as on REST read
					self.assertEqual(body["data"]["project_name"], data["project_name"])

	def test_finance_still_gets_the_amounts_back(self):
		data = self._project()
		data["total_costing_amount"] = 5200
		with self.set_user(FIN_USER):
			body = json.loads(_rest("/api/resource/Project", "POST", {"data": data}).get_data())
		self.assertEqual(body["data"]["total_costing_amount"], 5200)

	def test_rest_lists_and_counts_refuse_hidden_filters(self):
		with self.set_user(PM_USER):
			for path in (
				"/api/resource/Project",
				"/api/v2/document/Project",
				"/api/v2/doctype/Project/count",
			):
				for key in ("filters", "or_filters"):
					with self.subTest(path=path, key=key):
						response = _rest(
							path, "GET", {"data": [{"name": "PROJ-0001"}]}, {key: json.dumps(HIDDEN_COST)}
						)
						self.assertEqual(response.status_code, 403)
						self.assertNotIn("PROJ-0001", response.get_data(as_text=True))
			ok = _rest(
				"/api/resource/Project", "GET", {"data": []}, {"filters": json.dumps({"status": "Open"})}
			)
			self.assertEqual(ok.status_code, 200)

	def test_the_hook_is_registered(self):
		self.assertIn("vellox_agency.api_guard.after_request", frappe.get_hooks("after_request"))


class TestQuoteEstimate(_GuardCase):
	FIELDS = ("custom_vellox_estimate_hours", "custom_vellox_vendor_cost", "custom_vellox_estimated_margin")

	def test_project_managers_cannot_read_the_estimate(self):
		from vellox_agency.api_guard import ESTIMATE_PERMLEVEL

		meta = frappe.get_meta("Quotation")
		pm_levels = meta.get_permlevel_access("read", user=PM_USER)
		for field in self.FIELDS:
			with self.subTest(field=field):
				# The exact margin moved higher still, to Finance's level ([P3-143]).
				self.assertGreaterEqual(meta.get_field(field).permlevel, ESTIMATE_PERMLEVEL)
				self.assertNotIn(meta.get_field(field).permlevel, pm_levels)

	def test_operations_and_finance_keep_it(self):
		from vellox_agency.api_guard import ESTIMATE_PERMLEVEL

		meta = frappe.get_meta("Quotation")
		self.assertIn(ESTIMATE_PERMLEVEL, meta.get_permlevel_access("write", user=OPS_USER))
		self.assertIn(ESTIMATE_PERMLEVEL, meta.get_permlevel_access("read", user=FIN_USER))
		self.assertNotIn(ESTIMATE_PERMLEVEL, meta.get_permlevel_access("write", user=FIN_USER))

	def test_sales_and_the_agency_manager_keep_it(self):
		# Checked on the permission rows: creating those users would join lead routing.
		from vellox_agency.api_guard import ESTIMATE_PERMLEVEL

		for role in ("Vellox Sales", "Agency Manager"):
			with self.subTest(role=role):
				row = frappe.db.get_value(
					"Custom DocPerm",
					{"parent": "Quotation", "role": role, "permlevel": ESTIMATE_PERMLEVEL},
					["read", "write"],
					as_dict=True,
				)
				self.assertEqual((row.read, row.write), (1, 1))


class TestReviewFindings(_GuardCase):
	"""Routes found in the P4-34 security review."""

	def test_hidden_fields_inside_formulas_are_refused(self):
		from vellox_agency import api_guard

		with self.set_user(PM_USER):
			for fields in (
				["percent_complete + total_costing_amount as x"],
				["sum(percent_complete + total_costing_amount) as x"],
				json.dumps(["name", "percent_complete * 0 + `tabProject`.total_costing_amount as x"]),
			):
				with self.subTest(fields=fields):
					with self.assertRaises(frappe.PermissionError):
						api_guard.get_list("Project", fields=fields)
			with self.assertRaises(frappe.PermissionError):
				api_guard.get_value(
					"Project", "percent_complete + total_costing_amount", filters={"status": "Open"}
				)
			self.assertIsInstance(api_guard.get_list("Project", fields=["name", "percent_complete"]), list)
			# A lone hidden column is left to Frappe, which drops it, so saved layouts keep working.
			project = frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": f"_Test AG cols {frappe.generate_hash(length=5)}",
					"company": "_Test Company",
				}
			).insert(ignore_permissions=True)
			project.db_set("total_costing_amount", 5200)
			rows = api_guard.get_list(
				"Project", fields=["name", "total_costing_amount"], filters={"name": project.name}
			)
			self.assertEqual(rows[0].get("name"), project.name)
			self.assertNotIn(5200, rows[0].values())

	def test_other_spellings_and_child_fields_are_refused(self):
		from vellox_agency.api_guard import refuse_hidden_filters

		with self.set_user(PM_USER):
			with self.assertRaises(frappe.PermissionError):
				refuse_hidden_filters("Project", {"TOTAL_COSTING_AMOUNT": [">", 5000]})
			with self.assertRaises(frappe.PermissionError):
				refuse_hidden_filters(
					"Timesheet", {"costing_amount": [">", 10]}
				)  # Frappe moves it to the child

	def test_more_methods_refuse_hidden_filters(self):
		from vellox_agency import api_guard

		hidden = json.dumps(HIDDEN_COST)
		calls = {
			"frappe.client.get": lambda: api_guard.get("Project", filters=hidden),
			"get_stats": lambda: api_guard.get_stats(json.dumps(["status"]), "Project", hidden),
			"get_filter_dashboard_data": lambda: api_guard.get_filter_dashboard_data(
				json.dumps([{"name": "status"}]), "Project", hidden
			),
			"get_next filter": lambda: api_guard.get_next("Project", "x", 1, filters=hidden),
			"get_next sort": lambda: api_guard.get_next("Project", "x", 1, sort_field="total_costing_amount"),
			"calendar filters": lambda: api_guard.get_calendar_events(
				"Project", "2026-01-01", "2026-12-31", json.dumps({"start": "expected_start_date"}), hidden
			),
			"calendar field map": lambda: api_guard.get_calendar_events(
				"Project", "2026-01-01", "2026-12-31", json.dumps({"title": "total_costing_amount"})
			),
			"timesheet calendar": lambda: api_guard.get_timesheet_events(
				"2026-01-01", "2026-12-31", json.dumps([["Timesheet Detail", "costing_amount", ">", 10]])
			),
			"number card": lambda: api_guard.get_number_card_result(
				json.dumps(
					{
						"document_type": "Project",
						"function": "Sum",
						"aggregate_function_based_on": "total_costing_amount",
					}
				),
				"[]",
			),
			"validate_link": lambda: api_guard.validate_link(
				"Project", "PROJ-0001", json.dumps(["percent_complete + total_costing_amount as x"])
			),
			"map": lambda: api_guard.get_coords("Project", hidden, "coordinates"),
			"goal chart": lambda: api_guard.get_monthly_goal_graph_data(
				"t",
				"Project",
				"PROJ-0001",
				"total_costing_amount",
				"percent_complete",
				"notes",
				"Project",
				"name",
				"percent_complete",
				"creation",
			),
			"portal list": lambda: api_guard.get_list_data("Project", total_costing_amount=5200),
			"portal page": lambda: api_guard.get_portal_list("Project", total_costing_amount=5200),
			"report add column": lambda: api_guard.get_data_for_custom_field(
				"Project", "percent_complete + total_costing_amount"
			),
			"dashboard chart": lambda: api_guard.get_dashboard_chart(
				chart=json.dumps(
					{
						"document_type": "Project",
						"chart_type": "Sum",
						"value_based_on": "total_costing_amount",
						"based_on": "creation",
					}
				)
			),
		}
		with self.set_user(PM_USER):
			for name, call in calls.items():
				with self.subTest(method=name):
					with self.assertRaises(frappe.PermissionError):
						call()

	def test_document_methods_return_only_readable_fields(self):
		from vellox_agency.api_guard import run_doc_method

		project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"_Test AG RDM {frappe.generate_hash(length=5)}",
				"company": "_Test Company",
			}
		).insert(ignore_permissions=True)
		project.db_set("total_costing_amount", 5200)
		frappe.local.response = frappe._dict(docs=[])
		frappe.local.request = SimpleNamespace(method="POST")  # Frappe checks the HTTP method
		self.addCleanup(delattr, frappe.local, "request")
		with self.set_user(PM_USER):
			run_doc_method(
				"add_comment", dt="Project", dn=project.name, args=json.dumps({"text": "Checking"})
			)
		returned = [d for d in frappe.local.response.docs if d.get("name") == project.name]
		self.assertTrue(returned)
		self.assertFalse(returned[0].get("total_costing_amount"))

	def test_a_failing_rest_check_refuses_instead_of_sending_everything(self):
		from vellox_agency import api_guard

		with self.set_user(PM_USER), patch.object(api_guard, "_readable_body", side_effect=RuntimeError):
			response = _rest("/api/resource/Project", "POST", {"data": {"doctype": "Project", "name": "X"}})
		self.assertEqual(response.status_code, 500)
		self.assertNotIn('"name": "X"', response.get_data(as_text=True))

	def test_rest_lists_check_fields_and_child_lists(self):
		with self.set_user(PM_USER):
			response = _rest(
				"/api/resource/Project",
				"GET",
				{"data": [{"x": 5200}]},
				{"fields": json.dumps(["percent_complete + total_costing_amount as x"])},
			)
			self.assertEqual(response.status_code, 403)
		with self.set_user(FIN_USER):
			response = _rest(
				"/api/resource/Timesheet Detail",
				"GET",
				{"data": []},
				{"parent": "Timesheet", "filters": json.dumps({"costing_amount": [">", 1]})},
			)
			self.assertEqual(response.status_code, 200)  # Finance may read it


class TestEveryFilteringMethodIsReviewed(FrappeTestCase):
	def test_no_unreviewed_method_can_filter_a_money_doctype(self):
		from vellox_agency.api_guard import unreviewed_filtering_methods

		self.assertEqual(unreviewed_filtering_methods(), [])


class TestSecondReview(_GuardCase):
	"""Routes found in the second P4-34 review."""

	def test_searching_on_a_hidden_field_is_refused(self):
		from vellox_agency import api_guard

		with self.set_user(PM_USER):
			for call in (
				lambda: api_guard.query_task("Task", "1", "total_costing_amount", 0, 10, {}),
				lambda: api_guard.search_link("Task", "1", searchfield="total_costing_amount"),
				lambda: api_guard.search_widget("Task", "1", searchfield="TOTAL_COSTING_AMOUNT"),
			):
				with self.assertRaises(frappe.PermissionError):
					call()
			self.assertIsInstance(api_guard.query_task("Task", "", "subject", 0, 10, {}), list | tuple)

	def test_sorting_or_grouping_by_a_hidden_field_is_refused_in_any_case(self):
		from vellox_agency import api_guard

		with self.set_user(PM_USER):
			for kwargs in (
				{"order_by": "TOTAL_COSTING_AMOUNT desc"},
				{"order_by": "modified desc, total_costing_amount asc"},
				{"group_by": "Total_Costing_Amount"},
			):
				with self.subTest(**kwargs):
					with self.assertRaises(frappe.PermissionError):
						api_guard.get_list("Project", fields=["name"], **kwargs)
			frappe.local.form_dict = frappe._dict(
				doctype="Project", fields=json.dumps(["name"]), order_by="TOTAL_COSTING_AMOUNT desc"
			)
			with self.assertRaises(frappe.PermissionError):
				api_guard.reportview_get()
			self.assertIsInstance(
				api_guard.get_list("Project", fields=["name"], order_by="modified desc"), list
			)

	def test_joined_table_aliases_are_resolved(self):
		from vellox_agency.api_guard import refuse_hidden_fields

		with self.set_user(PM_USER):
			for field in (
				"`tabProject_1`.percent_complete + `tabProject_1`.total_costing_amount as x",
				"parent_project.percent_complete + parent_project.total_costing_amount as x",
				"`tabNo Such Table`.a + `tabNo Such Table`.b as x",
			):
				with self.subTest(field=field):
					with self.assertRaises(frappe.PermissionError):
						refuse_hidden_fields("Timesheet", [field], only_formulas=True)

	def test_next_and_previous_need_read_access(self):
		from vellox_agency import api_guard

		with self.set_user(PM_USER):
			with self.assertRaises(frappe.PermissionError):
				api_guard.get_next("Salary Slip", "x", 1)

	def test_documents_returned_as_dicts_are_filtered_too(self):
		from vellox_agency.api_guard import _filter_response_docs

		with self.set_user(PM_USER):
			frappe.local.response = frappe._dict(
				docs=[{"doctype": "Project", "name": "X", "project_name": "X", "total_costing_amount": 5200}]
			)
			_filter_response_docs()
			self.assertFalse(frappe.local.response.docs[0].get("total_costing_amount"))

	def test_the_money_doctypes_cover_every_hidden_field_setting(self):
		from vellox_agency.api_guard import MONEY_DOCTYPES
		from vellox_agency.setup.roles_rates import MONEY_FIELDS

		self.assertTrue(
			{*MONEY_FIELDS, "Quotation", "Project", "Task", "Activity Cost"} <= set(MONEY_DOCTYPES)
		)


class TestThirdReview(_GuardCase):
	"""Routes found in the third P4-34 review."""

	def test_a_search_query_goes_through_its_guard_whatever_doctype_is_named(self):
		from vellox_agency import api_guard

		kwargs = {"query": "erpnext.projects.utils.query_task"}
		api_guard._route_query_through_guard(kwargs, "Note")
		self.assertEqual(kwargs["query"], "vellox_agency.api_guard.query_task")

		task = frappe.get_doc({"doctype": "Task", "subject": "_Test AG search"}).insert(
			ignore_permissions=True
		)
		task.db_set("total_costing_amount", 1234)
		with self.set_user(PM_USER):
			for fn in (api_guard.search_link, api_guard.search_widget):
				with self.subTest(fn=fn.__name__):
					# Frappe turns the guard's refusal into an empty answer outside developer mode.
					try:
						rows = fn(
							"Note",
							"1",
							query="erpnext.projects.utils.query_task",
							searchfield="total_costing_amount",
						)
					except frappe.PermissionError:
						rows = []
					self.assertNotIn(task.name, json.dumps(rows, default=str))

	def test_custom_report_columns_cannot_carry_hidden_formulas(self):
		from vellox_agency.api_guard import refuse_hidden_report_columns

		column = {"fieldname": "progress + total_costing_amount", "doctype": "Task", "insert_after_index": 0}
		with self.set_user(PM_USER):
			for columns in (
				[column],
				json.dumps([column]),
				[{**column, "fieldname": "progress + total_costing_amount-task"}],
			):
				with self.subTest(columns=columns):
					with self.assertRaises(frappe.PermissionError):
						refuse_hidden_report_columns(columns)
			refuse_hidden_report_columns([{**column, "fieldname": "subject"}])

	def test_report_runs_and_saves_check_their_columns(self):
		from vellox_agency import report_guard

		column = json.dumps(
			[{"fieldname": "progress + total_costing_amount", "doctype": "Task", "insert_after_index": 0}]
		)
		with self.set_user(PM_USER):
			with self.assertRaises(frappe.PermissionError):
				report_guard.run("Project Summary", custom_columns=column)
			with self.assertRaises(frappe.PermissionError):
				report_guard.save_report("Project Summary", "_Test AG saved", column, "{}")

	def test_sort_formulas_with_commas_are_checked_whole(self):
		from vellox_agency import api_guard

		with self.set_user(PM_USER):
			with self.assertRaises(frappe.PermissionError):
				api_guard.get_list(
					"Project", fields=["name"], order_by="ifnull(TOTAL_COSTING_AMOUNT, 0) desc"
				)
			self.assertIsInstance(
				api_guard.get_list("Project", fields=["name"], order_by="ifnull(modified, 0) desc"), list
			)
