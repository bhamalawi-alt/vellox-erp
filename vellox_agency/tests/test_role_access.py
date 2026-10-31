"""Who can open and change what, per Vellox job ([P3-140], approved access table)."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from vellox_agency.security import JOB_PROFILES, setup_roles_and_permissions

EDIT, VIEW, NONE = "edit", "view", "none"


def _user(email, *roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "Access", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	frappe.get_doc("User", email).add_roles(*roles)
	return email


def _job_user(tag, profile):
	return _user(f"access-{profile.lower().replace(' ', '-')}-{tag}@example.com", *JOB_PROFILES[profile])


class TestRoleAccess(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.tests.test_offer_builder import TEST_CUSTOMER, _bootstrap_erpnext_test_fixtures

		_bootstrap_erpnext_test_fixtures()
		setup_roles_and_permissions()
		cls.customer = TEST_CUSTOMER

	def setUp(self):
		self.tag = frappe.generate_hash(length=8)
		# Assignment and sharing emails go through the email queue, which commits.
		for target in ("frappe.desk.form.assign_to.notify_assignment", "frappe.share.notify_assignment"):
			patcher = patch(target)
			patcher.start()
			self.addCleanup(patcher.stop)

	# --- record helpers -------------------------------------------------

	def _project(self, members=()):
		project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"_Test Access {self.tag} {frappe.generate_hash(length=4)}",
				"company": "_Test Company",
				"users": [{"user": member} for member in members],
			}
		)
		return project.insert(ignore_permissions=True)

	def _task(self, project):
		return frappe.get_doc(
			{"doctype": "Task", "subject": f"_Test Access Task {self.tag}", "project": project.name}
		).insert(ignore_permissions=True)

	def _timesheet(self, owner):
		with self.set_user(owner):
			return frappe.get_doc(
				{
					"doctype": "Timesheet",
					"company": "_Test Company",
					"time_logs": [{"hours": 1, "from_time": frappe.utils.now_datetime()}],
				}
			).insert(ignore_permissions=True)

	def _samples(self):
		"""One record per governed record type; unsaved where creating one needs full accounting."""
		return {
			"Lead": frappe.get_doc(
				{
					"doctype": "Lead",
					"lead_name": "_Test Access Lead",
					"email_id": f"access-lead-{frappe.generate_hash(length=10)}@example.com",
				}
			).insert(ignore_permissions=True),
			"Opportunity": frappe.new_doc("Opportunity"),
			"Quotation": frappe.new_doc("Quotation"),
			"Customer": frappe.get_doc("Customer", self.customer),
			"Project": self._project(),
			"Sales Invoice": frappe.new_doc("Sales Invoice"),
			"Payment Entry": frappe.new_doc("Payment Entry"),
		}

	def _level(self, user, doc):
		with self.set_user(user):
			if frappe.has_permission(doc.doctype, "write", doc=doc):
				return EDIT
			if frappe.has_permission(doc.doctype, "read", doc=doc):
				return VIEW
			return NONE

	def _assert_levels(self, profile, expected):
		user = _job_user(self.tag, profile)
		samples = self._samples()
		for doctype, level in expected.items():
			with self.subTest(profile=profile, doctype=doctype):
				self.assertEqual(self._level(user, samples[doctype]), level)

	# --- the approved table ---------------------------------------------

	def test_sales(self):
		self._assert_levels(
			"Sales",
			{"Lead": EDIT, "Opportunity": EDIT, "Quotation": EDIT, "Customer": EDIT,
			 "Project": NONE, "Sales Invoice": NONE, "Payment Entry": NONE},
		)

	def test_project_manager(self):
		self._assert_levels(
			"Project Manager",
			{"Project": EDIT, "Customer": VIEW, "Quotation": VIEW,
			 "Lead": NONE, "Opportunity": NONE, "Sales Invoice": NONE, "Payment Entry": NONE},
		)

	def test_finance(self):
		self._assert_levels(
			"Finance",
			{"Sales Invoice": EDIT, "Payment Entry": EDIT, "Customer": VIEW, "Quotation": VIEW,
			 "Project": VIEW, "Lead": NONE, "Opportunity": NONE},
		)

	def test_operations(self):
		self._assert_levels(
			"Operations",
			{"Quotation": EDIT, "Project": EDIT, "Lead": VIEW, "Opportunity": VIEW, "Customer": VIEW,
			 "Sales Invoice": NONE, "Payment Entry": NONE},
		)

	def test_agency_manager(self):
		self._assert_levels(
			"Agency Manager",
			{doctype: EDIT for doctype in ("Lead", "Opportunity", "Quotation", "Customer", "Project",
			                                "Sales Invoice", "Payment Entry")},
		)

	def test_team_member_sees_only_assigned_projects(self):
		for profile in ("Team Member", "Agency Staff"):
			with self.subTest(profile=profile):
				member = _job_user(self.tag, profile)
				mine, other = self._project(members=[member]), self._project()
				my_task, other_task = self._task(mine), self._task(other)
				self.assertEqual(self._level(member, mine), VIEW)
				self.assertEqual(self._level(member, other), NONE)
				self.assertEqual(self._level(member, my_task), EDIT)
				self.assertEqual(self._level(member, other_task), NONE)
				with self.set_user(member):
					projects = frappe.get_list("Project", filters={"name": ["in", [mine.name, other.name]]}, pluck="name")
					tasks = frappe.get_list("Task", filters={"name": ["in", [my_task.name, other_task.name]]}, pluck="name")
				self.assertEqual(projects, [mine.name])
				self.assertEqual(tasks, [my_task.name])
				for doctype in ("Lead", "Quotation", "Customer", "Sales Invoice"):
					self.assertEqual(self._level(member, self._samples()[doctype]), NONE, doctype)

	def test_team_member_sees_only_their_own_timesheets(self):
		member = _job_user(self.tag, "Team Member")
		colleague = _job_user(f"{self.tag}b", "Team Member")
		mine, theirs = self._timesheet(member), self._timesheet(colleague)
		self.assertEqual(self._level(member, mine), EDIT)
		self.assertEqual(self._level(member, theirs), NONE)
		with self.set_user(member):
			listed = frappe.get_list("Timesheet", filters={"name": ["in", [mine.name, theirs.name]]}, pluck="name")
		self.assertEqual(listed, [mine.name])

	def test_lists_hide_record_types_a_job_cannot_see(self):
		self._samples()  # makes sure at least one Lead exists
		sales_only = _job_user(self.tag, "Project Manager")
		with self.set_user(sales_only):
			self.assertEqual(frappe.get_list("Lead", limit=1), [])

	def test_role_profiles_exist_for_every_job(self):
		for profile, roles in JOB_PROFILES.items():
			with self.subTest(profile=profile):
				name = f"Vellox {profile}" if not profile.startswith("Agency") else profile
				doc = frappe.get_doc("Role Profile", name)
				self.assertEqual(sorted(r.role for r in doc.roles), sorted(roles))

	def test_hooks_cover_every_governed_record_type(self):
		from vellox_agency import hooks
		from vellox_agency.security import GOVERNED_DOCTYPES

		self.assertEqual(set(hooks.JOB_ACCESS_DOCTYPES), set(GOVERNED_DOCTYPES) | {"Deliverable"})
		for doctype in hooks.JOB_ACCESS_DOCTYPES:
			with self.subTest(doctype=doctype):
				self.assertIn("vellox_agency.security.job_access_permission", frappe.get_hooks("has_permission").get(doctype, []))
				self.assertIn("vellox_agency.security.job_access_query", frappe.get_hooks("permission_query_conditions").get(doctype, []))

	def test_salespeople_now_receive_leads(self):
		from vellox_agency.crm_setup import lead_assignment_roster

		seller = _job_user(self.tag, "Sales")
		self.assertIn(seller, lead_assignment_roster())
