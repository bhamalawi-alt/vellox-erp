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

	# --- gaps from the PR #33 security review and owner decisions of 2026-10-31 ---

	def _new(self, doctype, **fields):
		doc = frappe.new_doc(doctype)
		doc.update(fields)
		return doc

	def _deliverable(self, project):
		return frappe.get_doc(
			{"doctype": "Deliverable", "project": project.name, "title": f"_Test Access {self.tag}",
			 "deliverable_type": "Design"}
		).insert(ignore_permissions=True)

	def test_levels_for_contacts_items_tasks_and_timesheets(self):
		cases = {
			"Sales": {"Contact": EDIT, "Item": VIEW},
			"Project Manager": {"Contact": VIEW, "Task": EDIT},
			"Finance": {"Task": NONE},
			"Operations": {"Task": EDIT},
			"Team Member": {"Contact": NONE, "Item": NONE},
		}
		project = self._project()
		for profile, expected in cases.items():
			user = _job_user(self.tag, profile)
			samples = {"Contact": self._new("Contact", first_name="Access"), "Item": self._new("Item"),
			           "Task": self._task(project)}
			for doctype, level in expected.items():
				with self.subTest(profile=profile, doctype=doctype):
					self.assertEqual(self._level(user, samples[doctype]), level)

	def test_timesheet_levels_by_job(self):
		owner = _job_user(f"{self.tag}o", "Team Member")
		sheet = self._timesheet(owner)
		for profile, level in (("Project Manager", EDIT), ("Finance", VIEW), ("Operations", VIEW)):
			with self.subTest(profile=profile):
				self.assertEqual(self._level(_job_user(self.tag, profile), sheet), level)

	def test_money_and_cost_records_follow_the_owner_decision(self):
		money = ("Sales Order", "Delivery Note", "POS Invoice", "Account", "Cost Center")
		for profile in ("Sales", "Project Manager", "Operations"):
			user = _job_user(self.tag, profile)
			for doctype in ("Sales Order", "Delivery Note", "POS Invoice"):
				with self.subTest(profile=profile, doctype=doctype):
					self.assertEqual(self._level(user, self._new(doctype)), NONE)
			# Accounts and cost centers: hidden from lists and link search, but
			# readable behind the scenes because ERPNext reads them when a quote saves.
			for doctype in ("Account", "Cost Center"):
				with self.subTest(profile=profile, doctype=doctype), self.set_user(user):
					self.assertEqual(frappe.get_list(doctype, limit=1), [])
					self.assertFalse(frappe.has_permission(doctype, "write", doc=self._new(doctype)))
		finance = _job_user(self.tag, "Finance")
		for doctype in money:
			with self.subTest(profile="Finance", doctype=doctype):
				self.assertNotEqual(self._level(finance, self._new(doctype)), NONE)
		member = _job_user(self.tag, "Team Member")
		for doctype in ("Activity Cost", "Quality Goal", "Project Template"):
			with self.subTest(profile="Team Member", doctype=doctype):
				self.assertEqual(self._level(member, self._new(doctype)), NONE)
		pm = _job_user(self.tag, "Project Manager")
		self.assertEqual(self._level(pm, self._new("Project Template")), VIEW)
		self.assertNotEqual(self._level(pm, self._new("Activity Cost")), NONE)

	def test_view_only_save_is_refused_but_links_still_work(self):
		finance = _job_user(self.tag, "Finance")
		project = self._project()
		with self.set_user(finance):
			fresh = frappe.get_doc("Project", project.name)  # not the ignore_permissions copy
			fresh.notes = "edited by finance"
			self.assertRaises(frappe.PermissionError, fresh.save)
		pm = _job_user(self.tag, "Project Manager")
		with self.set_user(pm):
			self.assertTrue(frappe.has_permission("Customer", "select", doc=frappe.get_doc("Customer", self.customer)))

	def test_team_member_deliverables_and_project_updates_are_scoped(self):
		member = _job_user(self.tag, "Team Member")
		mine, other = self._project(members=[member]), self._project()
		my_deliverable, other_deliverable = self._deliverable(mine), self._deliverable(other)
		self.assertNotEqual(self._level(member, my_deliverable), NONE)
		self.assertEqual(self._level(member, other_deliverable), NONE)
		updates = [
			frappe.get_doc({"doctype": "Project Update", "project": p.name, "date": frappe.utils.today()}).insert(
				ignore_permissions=True
			)
			for p in (mine, other)
		]
		with self.set_user(member):
			deliverables = frappe.get_list("Deliverable", filters={"name": ["in", [my_deliverable.name, other_deliverable.name]]}, pluck="name")
			listed_updates = frappe.get_list("Project Update", filters={"name": ["in", [u.name for u in updates]]}, pluck="name")
		self.assertEqual(deliverables, [my_deliverable.name])
		self.assertEqual(listed_updates, [updates[0].name])

	def test_team_member_cannot_log_time_on_another_project(self):
		member = _job_user(self.tag, "Team Member")
		other = self._project()
		with self.set_user(member):
			sheet = frappe.get_doc(
				{"doctype": "Timesheet", "company": "_Test Company",
				 "time_logs": [{"hours": 1, "from_time": frappe.utils.now_datetime(), "project": other.name}]}
			)
			self.assertRaises(frappe.PermissionError, sheet.insert)

	def test_file_lists_hide_attachments_of_records_a_job_cannot_see(self):
		member = _job_user(self.tag, "Team Member")
		mine, other = self._project(members=[member]), self._project()
		files = [
			frappe.get_doc(
				{"doctype": "File", "file_name": f"access-{self.tag}-{p.name}.txt", "content": b"x",
				 "attached_to_doctype": "Project", "attached_to_name": p.name, "is_private": 1}
			).insert(ignore_permissions=True)
			for p in (mine, other)
		]
		with self.set_user(member):
			listed = frappe.get_list("File", filters={"name": ["in", [f.name for f in files]]}, pluck="name")
		self.assertEqual(listed, [files[0].name])

	def test_shares_and_assignments_cannot_exceed_a_job(self):
		from frappe.desk.form.assign_to import add as assign

		member = _job_user(self.tag, "Team Member")
		finance = _job_user(self.tag, "Finance")
		seller = _job_user(self.tag, "Sales")
		project = self._project()
		self.assertRaises(frappe.PermissionError, frappe.share.add, "Project", project.name, member)
		self.assertRaises(frappe.PermissionError, frappe.share.add, "Project", project.name, finance, write=1)
		frappe.share.add("Project", project.name, finance)  # read-only share is within Finance's job
		self.assertRaises(frappe.PermissionError, frappe.share.add, "Project", project.name, everyone=1)
		self.assertRaises(
			frappe.PermissionError, assign, {"assign_to": [seller], "doctype": "Project", "name": project.name}
		)
		# Adding someone to Project > Users is how membership is granted; ERPNext
		# shares the project with them as part of that save, which must still work.
		pm = _job_user(self.tag, "Project Manager")
		with self.set_user(pm):
			fresh = frappe.get_doc("Project", project.name)
			fresh.append("users", {"user": member})
			fresh.save()
		self.assertEqual(self._level(member, frappe.get_doc("Project", project.name)), VIEW)

	def test_role_profile_assignment_and_mixed_jobs(self):
		user = _user(f"access-profiled-{self.tag}@example.com")
		doc = frappe.get_doc("User", user)
		doc.role_profile_name = "Vellox Sales"
		doc.save(ignore_permissions=True)
		self.assertTrue(set(JOB_PROFILES["Sales"]) <= set(frappe.get_roles(user)))
		samples = self._samples()
		self.assertEqual(self._level(user, samples["Lead"]), EDIT)
		mixed = _user(f"access-mixed-{self.tag}@example.com", *JOB_PROFILES["Project Manager"], *JOB_PROFILES["Finance"])
		self.assertEqual(self._level(mixed, samples["Project"]), EDIT)
		self.assertEqual(self._level(mixed, samples["Sales Invoice"]), EDIT)

	def test_capped_jobs_can_still_do_their_daily_work(self):
		from erpnext.selling.doctype.quotation.test_quotation import make_quotation

		from vellox_agency.tests.test_offer_builder import TEST_PRICE_LIST

		seller = _job_user(self.tag, "Sales")
		with self.set_user(seller):
			quote = make_quotation(
				item="_Test Vellox Iso Service" if frappe.db.exists("Item", "_Test Vellox Iso Service") else None,
				party_name=self.customer, selling_price_list=TEST_PRICE_LIST, warehouse="", qty=1, rate=100,
				do_not_save=True,
			)
			quote.insert()
		pm = _job_user(self.tag, "Project Manager")
		project = self._project()
		cost_center = frappe.db.get_value("Cost Center", {"company": "_Test Company", "is_group": 0})
		project.db_set("cost_center", cost_center)
		with self.set_user(pm):
			fresh = frappe.get_doc("Project", project.name)
			fresh.notes = "PM edit with a cost center set"
			fresh.save()

	# --- gaps from the PR #33 re-review ------------------------------------

	def _call(self, user, cmd, **kwargs):
		"""Call a whitelisted method as frappe.handler.execute_cmd does, overrides included."""
		from frappe.handler import get_attr

		fn = get_attr(frappe.override_whitelisted_method(cmd))
		with self.set_user(user):
			frappe.is_whitelisted(fn)
			return fn(**kwargs)

	def test_account_balances_are_only_for_finance_and_managers(self):
		import json

		account = frappe.db.get_value("Account", {"company": "_Test Company", "is_group": 0})
		payload = {"accounts": json.dumps([{"value": account, "account_currency": ""}]), "company": "_Test Company"}
		for profile in ("Sales", "Project Manager", "Operations"):
			with self.subTest(profile=profile):
				self.assertRaises(
					frappe.PermissionError, self._call, _job_user(self.tag, profile),
					"erpnext.accounts.utils.get_account_balances", **payload,
				)
		result = self._call(_job_user(self.tag, "Finance"), "erpnext.accounts.utils.get_account_balances", **payload)
		self.assertIn("balance", result[0])

	def test_team_member_cannot_log_time_on_another_projects_task(self):
		member = _job_user(self.tag, "Team Member")
		mine, other = self._project(members=[member]), self._project()
		foreign_task = self._task(other)
		with self.set_user(member):
			sheet = frappe.get_doc(
				{"doctype": "Timesheet", "company": "_Test Company",
				 "time_logs": [{"hours": 1, "from_time": frappe.utils.now_datetime(),
				                "project": mine.name, "task": foreign_task.name}]}
			)
			self.assertRaises(frappe.PermissionError, sheet.insert)

	def test_rule_breaking_shares_can_be_revoked_and_are_cleaned_up(self):
		from vellox_agency.security import revoke_shares_beyond_jobs

		seller, finance = _job_user(self.tag, "Sales"), _job_user(self.tag, "Finance")
		project = self._project()
		legacy = []
		for user in (seller, finance):  # shares from before this change bypassed the new check
			share = frappe.get_doc(
				{"doctype": "DocShare", "share_doctype": "Project", "share_name": project.name, "user": user,
				 "read": 1, "write": 1}
			)
			share.db_insert()
			legacy.append(share.name)
		frappe.share.set_permission("Project", project.name, seller, "write", 0)  # lowering rights is allowed
		self.assertEqual(frappe.db.get_value("DocShare", legacy[0], "write"), 0)
		revoke_shares_beyond_jobs()
		self.assertFalse(frappe.db.exists("DocShare", legacy[0]), "Sales cannot see projects at all")
		self.assertEqual(frappe.db.get_value("DocShare", legacy[1], ["read", "write"]), (1, 0))
