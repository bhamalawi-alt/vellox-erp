"""Who may delete and export ([P3-141], owner decision 2026-11-01).

Deleting: the Agency Manager deletes anything governed; everyone else only their
own drafts. Exporting lists: the Agency Manager and Finance.
"""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

SALES = "dx-sales@example.com"
PROJECTS = "dx-projects@example.com"
OTHER = "dx-other@example.com"


def _user(email, *roles):
	# Only standard ERPNext roles: the job is set per test by patching _job_roles,
	# so no Vellox Sales / Agency Manager user joins lead routing on the test site.
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": "DX", "send_welcome_email": 0}).insert(
			ignore_permissions=True
		)
		frappe.get_doc("User", email).add_roles(*roles)
	return email


@contextmanager
def _as_job(*jobs):
	with patch("vellox_agency.security._job_roles", return_value=set(jobs)):
		yield


def _can_delete(doc, user):
	return frappe.has_permission(doc.doctype, "delete", doc=doc, user=user)


class _DeleteCase(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.security import setup_roles_and_permissions
		from vellox_agency.tests.test_offer_builder import _bootstrap_erpnext_test_fixtures

		_bootstrap_erpnext_test_fixtures()
		setup_roles_and_permissions()
		_user(SALES, "Sales User")
		_user(PROJECTS, "Projects User", "Projects Manager", "Sales User")
		_user(OTHER, "Sales User", "Projects User")

	def _owned(self, doc, owner):
		doc.db_set("owner", owner, update_modified=False)
		doc.reload()
		return doc

	def _quote(self, owner):
		from vellox_agency.tests.test_quotation_actions import _real_quote

		return self._owned(_real_quote(0), owner)

	def _task(self, owner, status="Open"):
		task = frappe.get_doc({"doctype": "Task", "subject": f"DX {frappe.generate_hash(length=6)}"}).insert(
			ignore_permissions=True
		)
		task.db_set("status", status, update_modified=False)
		return self._owned(task, owner)


class TestDeleteOwnDrafts(_DeleteCase):
	def test_a_salesperson_deletes_their_own_draft_quote(self):
		with _as_job("Vellox Sales"):
			self.assertTrue(_can_delete(self._quote(SALES), SALES))

	def test_not_someone_elses_draft_quote(self):
		with _as_job("Vellox Sales"):
			self.assertFalse(_can_delete(self._quote(OTHER), SALES))

	def test_leads_are_for_managers(self):
		# ERPNext's Sales User has no delete right on Lead, so even a salesperson's
		# own new lead is deleted by a manager.
		from vellox_agency.tests.test_pipeline import _make_qualified_lead

		lead = self._owned(_make_qualified_lead(), SALES)
		with _as_job("Vellox Sales"):
			self.assertFalse(_can_delete(lead, SALES))

	def test_their_own_open_opportunity_but_not_one_further_along(self):
		from vellox_agency.tests.test_pipeline import _make_opportunity, _make_qualified_lead

		opp = self._owned(_make_opportunity(_make_qualified_lead().name), SALES)
		with _as_job("Vellox Sales"):
			self.assertTrue(_can_delete(opp, SALES))
			opp.db_set("status", "Replied", update_modified=False)
			opp.reload()
			self.assertFalse(_can_delete(opp, SALES))

	def test_their_own_open_task_but_not_one_in_progress(self):
		with _as_job("Vellox Project Manager"):
			self.assertTrue(_can_delete(self._task(PROJECTS), PROJECTS))
			self.assertFalse(_can_delete(self._task(PROJECTS, status="Working"), PROJECTS))
			self.assertFalse(_can_delete(self._task(OTHER), PROJECTS))

	def test_projects_are_for_managers_even_when_new(self):
		project = frappe.get_doc(
			{"doctype": "Project", "project_name": f"_Test DX {frappe.generate_hash(length=6)}", "company": "_Test Company"}
		).insert(ignore_permissions=True)
		project = self._owned(project, PROJECTS)
		with _as_job("Vellox Project Manager"):
			self.assertFalse(_can_delete(project, PROJECTS))
		with _as_job("Agency Manager"):
			self.assertTrue(_can_delete(project, PROJECTS))


class TestManagersDelete(_DeleteCase):
	def test_the_agency_manager_deletes_others_records(self):
		with _as_job("Agency Manager"):
			self.assertTrue(_can_delete(self._quote(OTHER), PROJECTS))
			self.assertTrue(_can_delete(self._task(OTHER, status="Working"), PROJECTS))

	def test_users_without_a_job_are_not_capped(self):
		# Administrator and System Managers keep ERPNext's own rules.
		with _as_job():
			self.assertTrue(_can_delete(self._quote(OTHER), PROJECTS))


EXPORT_ROUTES = {
	"frappe.desk.reportview.export_query": "vellox_agency.export_guard.export_query",
	"frappe.desk.query_report.export_query": "vellox_agency.export_guard.export_report",
	"frappe.core.doctype.data_export.exporter.export_data": "vellox_agency.export_guard.export_data",
	"frappe.core.doctype.data_import.data_import.download_template": "vellox_agency.export_guard.download_template",
	"frappe.utils.print_format.download_multi_pdf": "vellox_agency.export_guard.download_multi_pdf",
	"frappe.utils.print_format.download_multi_pdf_async": "vellox_agency.export_guard.download_multi_pdf_async",
	"frappe.contacts.doctype.contact.contact.download_vcards": "vellox_agency.export_guard.download_vcards",
}


class TestExport(FrappeTestCase):

	def test_only_finance_and_the_agency_manager_export(self):
		from vellox_agency.export_guard import can_export_lists

		cases = {
			("Vellox Finance",): True,
			("Agency Manager",): True,
			("Vellox Sales",): False,
			("Vellox Project Manager",): False,
			("Vellox Operations",): False,
			("Vellox Team Member",): False,
			("Vellox Sales", "Vellox Finance"): True,
			(): True,  # no job: ERPNext's own export rights apply
		}
		for jobs, expected in cases.items():
			with self.subTest(jobs=jobs), _as_job(*jobs):
				self.assertEqual(can_export_lists("someone@example.com"), expected)

	def test_every_export_route_is_guarded(self):
		overrides = frappe.get_hooks("override_whitelisted_methods")
		for original, guard in EXPORT_ROUTES.items():
			with self.subTest(route=original):
				self.assertEqual(overrides.get(original), [guard])

	def test_a_guarded_export_is_refused_before_any_data_is_read(self):
		from vellox_agency import export_guard

		for name in ("export_query", "export_report", "export_data", "download_vcards"):
			with self.subTest(route=name), _as_job("Vellox Sales"):
				with patch.object(export_guard, "_original", side_effect=AssertionError("data read")):
					with self.assertRaises(frappe.PermissionError):
						getattr(export_guard, name)()

	def test_a_blank_import_template_is_still_allowed(self):
		from vellox_agency import export_guard

		with _as_job("Vellox Sales"), patch.object(export_guard, "_original", return_value="template") as original:
			self.assertEqual(export_guard.download_template(doctype="Lead", export_records="blank_template"), "template")
			original.assert_called_once()
			with self.assertRaises(frappe.PermissionError):
				export_guard.download_template(doctype="Lead", export_records="all")

	def test_bulk_print_is_an_export(self):
		from vellox_agency import export_guard

		for name in ("download_multi_pdf", "download_multi_pdf_async"):
			with self.subTest(route=name), _as_job("Vellox Sales"):
				with patch.object(export_guard, "_original", side_effect=AssertionError("data read")):
					with self.assertRaises(frappe.PermissionError):
						getattr(export_guard, name)(doctype="Lead", name='["x", "y"]')


class TestExportWithRealJobs(FrappeTestCase):
	"""The real job profiles, through Frappe's request handler."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.security import JOB_PROFILES, setup_roles_and_permissions
		from vellox_agency.tests.test_offer_builder import _bootstrap_erpnext_test_fixtures

		_bootstrap_erpnext_test_fixtures()
		setup_roles_and_permissions()
		cls.finance = _user("dx-finance@example.com", *JOB_PROFILES["Finance"])
		cls.pm = _user("dx-pm@example.com", *JOB_PROFILES["Project Manager"])

	def _export_customers(self, user):
		from frappe.handler import execute_cmd

		frappe.local.response = frappe._dict()
		previous = getattr(frappe.local, "request", None)
		frappe.local.request = SimpleNamespace(method="POST", headers={})
		try:
			with self.set_user(user):
				# After set_user, which replaces the request's form_dict.
				frappe.local.form_dict = frappe._dict(
					doctype="Customer", fields='["`tabCustomer`.`name`"]', file_format_type="CSV", cmd="x"
				)
				execute_cmd("frappe.desk.reportview.export_query")
		finally:
			frappe.local.request = previous
		return frappe.local.response

	def test_finance_exports_the_customer_list(self):
		response = self._export_customers(self.finance)
		self.assertEqual(response.type, "binary")
		self.assertTrue(response.filename.endswith(".csv"), response.filename)

	def test_a_project_manager_is_refused(self):
		with self.assertRaisesRegex(frappe.PermissionError, "Finance and the Agency Manager"):
			self._export_customers(self.pm)

	def test_finance_exports_only_lists_its_job_can_see(self):
		# Query reports run their own SQL, so an export right on a list Finance
		# cannot see would hand over every row of it.
		from frappe.permissions import can_export

		with self.set_user(self.finance):
			self.assertTrue(can_export("Customer"))
			for doctype in ("Lead", "Opportunity", "Task"):
				with self.subTest(doctype=doctype):
					self.assertFalse(can_export(doctype))

	def test_an_earlier_grant_on_hidden_lists_is_removed(self):
		from frappe.permissions import add_permission, setup_custom_perms, update_permission_property

		from vellox_agency.security import grant_finance_export

		setup_custom_perms("Lead")
		if not frappe.db.exists("Custom DocPerm", {"parent": "Lead", "role": "Vellox Finance", "permlevel": 0}):
			add_permission("Lead", "Vellox Finance", 0)
		update_permission_property("Lead", "Vellox Finance", 0, "export", 1, validate=False)
		grant_finance_export()
		self.assertFalse(frappe.db.exists("Custom DocPerm", {"parent": "Lead", "role": "Vellox Finance"}))
