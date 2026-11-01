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
		for field in self.FIELDS:
			with self.subTest(field=field):
				self.assertEqual(meta.get_field(field).permlevel, ESTIMATE_PERMLEVEL)
		self.assertNotIn(ESTIMATE_PERMLEVEL, meta.get_permlevel_access("read", user=PM_USER))

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
