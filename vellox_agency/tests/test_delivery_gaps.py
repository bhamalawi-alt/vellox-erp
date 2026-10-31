"""Delivery plan items that were missing from the code ([P3-99])."""

import ast
import unittest.mock
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from vellox_agency.tests.test_delivery_notifications import _outgoing_email_account, _queued


def _user(email, *roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": "Gaps", "send_welcome_email": 0}).insert(
			ignore_permissions=True
		)
		frappe.get_doc("User", email).add_roles(*roles)
	return email


def _test_item():
	"""The quote helpers' service item, made as Administrator before tests switch user."""
	from erpnext.stock.doctype.item.test_item import make_item

	if not frappe.db.exists("Item", "_Test Vellox Actions Service"):
		make_item("_Test Vellox Actions Service", {"is_stock_item": 0, "stock_uom": "Unit"})


PM = "gaps-pm@example.com"
MEMBER = "gaps-member@example.com"
SALES = "gaps-sales@example.com"
OPS = "gaps-ops@example.com"


class _GapsCase(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.security import apply_baseline
		from vellox_agency.tests.test_offer_builder import _bootstrap_erpnext_test_fixtures

		_bootstrap_erpnext_test_fixtures()
		apply_baseline()
		_outgoing_email_account()
		_user(PM, "Vellox Project Manager", "Projects User", "Projects Manager")
		_user(MEMBER, "Vellox Team Member", "Projects User")
		# Sales User only: a "Vellox Sales" user would join lead routing on the test
		# site, and the assignment emails then commit other modules' test leads.
		_user(SALES, "Sales User")
		_user(OPS, "Vellox Operations", "Sales User")
		_test_item()

	def setUp(self):
		# The digest goes to every Operations user; keep other tests' users out of it.
		frappe.db.delete("Email Queue")

	def _project(self, **kw):
		return frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"_Test Gaps {frappe.generate_hash(length=8)}",
				"company": "_Test Company",
				**kw,
			}
		).insert(ignore_permissions=True)


class TestProjectFields(_GapsCase):
	def test_project_has_phase_risks_and_manager_fields(self):
		meta = frappe.get_meta("Project")
		self.assertEqual(
			meta.get_field("custom_vellox_phase").options.split("\n"),
			["", "Discovery", "Design", "Build", "Launch", "Post-Launch"],
		)
		self.assertEqual(meta.get_field("custom_vellox_risks").fieldtype, "Small Text")
		self.assertEqual(meta.get_field("custom_vellox_project_manager").options, "User")
		self.assertTrue(meta.track_changes, "phase changes must be kept in the history")

	def test_whoever_creates_a_project_is_its_manager(self):
		with self.set_user(PM):
			project = frappe.get_doc(
				{"doctype": "Project", "project_name": f"_Test Gaps {frappe.generate_hash(length=8)}", "company": "_Test Company"}
			).insert()
		self.assertEqual(project.custom_vellox_project_manager, PM)

	def test_a_chosen_manager_is_kept(self):
		project = self._project(custom_vellox_project_manager=PM)
		self.assertEqual(project.custom_vellox_project_manager, PM)


class TestProjectPhase(_GapsCase):
	def _phase(self, project):
		return frappe.db.get_value("Project", project, "custom_vellox_phase")

	def _complete(self, task_names):
		for name in task_names:
			task = frappe.get_doc("Task", name)
			task.status = "Completed"
			task.save(ignore_permissions=True)

	def _tasks_in(self, project, phase):
		return frappe.get_all(
			"Task", filters={"project": project, "custom_vellox_phase": phase}, pluck="name", order_by="creation asc"
		)

	def test_phase_follows_the_earliest_open_work(self):
		from vellox_agency.acceptance import create_project_from_template

		project = create_project_from_template("Vellox — Web Development")["project"]
		self.assertEqual(self._phase(project), "Discovery")
		self._complete(self._tasks_in(project, "Discovery"))
		self.assertEqual(self._phase(project), "Build")
		self._complete(self._tasks_in(project, "Build"))
		self.assertEqual(self._phase(project), "Launch")
		self._complete(self._tasks_in(project, "Launch"))
		self.assertEqual(self._phase(project), "Post-Launch")

	def test_reopening_a_task_moves_the_phase_back(self):
		from vellox_agency.acceptance import create_project_from_template

		project = create_project_from_template("Vellox — Web Development")["project"]
		discovery = self._tasks_in(project, "Discovery")
		self._complete(discovery)
		task = frappe.get_doc("Task", discovery[0])
		task.status = "Open"
		task.save(ignore_permissions=True)
		self.assertEqual(self._phase(project), "Discovery")

	def test_moving_a_task_updates_both_projects(self):
		from vellox_agency.acceptance import create_project_from_template

		source = create_project_from_template("Vellox — Web Development")["project"]
		target = self._project()
		task = frappe.get_doc("Task", self._tasks_in(source, "Discovery")[0])
		task.project = target.name
		task.save(ignore_permissions=True)
		self.assertEqual(self._phase(source), "Build")  # its only Discovery task left
		self.assertEqual(self._phase(target.name), "Discovery")

	def test_a_project_without_phased_tasks_keeps_its_typed_phase(self):
		project = self._project(custom_vellox_phase="Design")
		frappe.get_doc({"doctype": "Task", "subject": "Unphased", "project": project.name}).insert(
			ignore_permissions=True
		)
		self.assertEqual(self._phase(project.name), "Design")


class TestDeliveryAlerts(_GapsCase):
	def test_new_project_emails_its_manager(self):
		project = self._project(custom_vellox_project_manager=PM)
		self.assertIn(("Project created: " + project.project_name, {PM}), _queued(project))

	def test_deliverable_client_review_emails_the_project_manager(self):
		from vellox_agency.deliverable import transition

		project = self._project(custom_vellox_project_manager=PM)
		doc = frappe.get_doc(
			{"doctype": "Deliverable", "project": project.name, "title": "Gaps review", "deliverable_type": "Design"}
		).insert(ignore_permissions=True)
		for action in ("submit_for_review", "internal_approve"):
			transition(doc, action)
			doc.save(ignore_permissions=True)
		review = [r for m, r in _queued(doc) if "Deliverable sent to client review" in m]
		self.assertEqual(review, [{PM}])

	def test_client_review_on_a_project_without_a_manager_emails_the_owner(self):
		from vellox_agency.deliverable import transition

		project = self._project()
		project.db_set("custom_vellox_project_manager", None)  # projects from before [P3-99]
		with self.set_user(MEMBER):
			doc = frappe.get_doc(
				{"doctype": "Deliverable", "project": project.name, "title": "Gaps no PM", "deliverable_type": "Design"}
			).insert(ignore_permissions=True)
		for action in ("submit_for_review", "internal_approve"):
			transition(doc, action)
			doc.save(ignore_permissions=True)
		review = [r for m, r in _queued(doc) if "Deliverable sent to client review" in m]
		self.assertEqual(review, [{MEMBER}])

	def test_change_request_decision_emails_the_project_team(self):
		project = self._project(custom_vellox_project_manager=PM, users=[{"user": MEMBER}])
		cr = frappe.get_doc(
			{"doctype": "Vellox Change Request", "project": project.name, "title": "Gaps CR", "status": "Draft"}
		).insert(ignore_permissions=True)
		for status in ("Under Review", "Rejected"):
			cr.status = status
			cr.save(ignore_permissions=True)
		decision = [r for m, r in _queued(cr) if "Change Request" in m]
		self.assertEqual(len(decision), 1, _queued(cr))
		self.assertTrue({PM, MEMBER} <= decision[0], decision)


class TestSalesAlerts(_GapsCase):
	def test_approved_quote_emails_its_salesperson(self):
		from vellox_agency.approval import approve_quotation
		from vellox_agency.tests.test_quotation_actions import _ops_tier_quote

		with self.set_user(SALES):
			quote = _ops_tier_quote()
		with self.set_user(OPS):
			approve_quotation(quote.name)
		approved = [r for m, r in _queued(quote) if "approved" in m.lower()]
		self.assertEqual(approved, [{SALES}])

	def test_auto_approved_quote_sends_no_approval_email(self):
		from vellox_agency.tests.test_quotation_actions import _real_quote

		with self.set_user(SALES):
			quote = _real_quote(0)
		self.assertEqual(quote.custom_vellox_approved_by, "auto")
		self.assertEqual([m for m, _ in _queued(quote) if "approved" in m.lower()], [])

	def _lead(self, **kw):
		return frappe.get_doc(
			{
				"doctype": "Lead",
				"first_name": "Gaps",
				"lead_name": "Gaps Prospect",
				"email_id": f"prospect-{frappe.generate_hash(length=6)}@example.com",
				**kw,
			}
		).insert(ignore_permissions=True)

	def test_website_inquiry_gets_an_acknowledgement(self):
		lead = self._lead(custom_vellox_inquiry="We need a new website.")
		acks = [r for m, r in _queued(lead) if "Thank you" in m]
		self.assertEqual(acks, [{lead.email_id}])

	def test_acknowledgement_does_not_repeat_what_the_visitor_typed(self):
		# Anyone can post an inquiry for any address; echoing the name would let them
		# send their own text (e.g. a phishing link) from Vellox's mail server.
		lead = self._lead(
			first_name="Verify at evil.example", lead_name="Verify at evil.example", custom_vellox_inquiry="Hi"
		)
		messages = frappe.get_all(
			"Email Queue", filters={"reference_doctype": "Lead", "reference_name": lead.name}, pluck="message"
		)
		self.assertEqual(len(messages), 1)
		self.assertNotIn("evil.example", messages[0])

	def test_lead_typed_in_by_staff_gets_no_acknowledgement(self):
		lead = self._lead()
		self.assertEqual(_queued(lead), [])

	def test_late_reply_digest_lists_overdue_open_leads_for_operations(self):
		from vellox_agency.lead_followup import send_late_reply_digest

		overdue = self._lead()
		frappe.db.set_value("Lead", overdue.name, "custom_vellox_first_response_due", add_to_date(now_datetime(), hours=-1))
		answered = self._lead()
		frappe.db.set_value(
			"Lead",
			answered.name,
			{"custom_vellox_first_response_due": add_to_date(now_datetime(), hours=-1), "status": "Replied"},
		)
		on_time = self._lead()

		send_late_reply_digest()
		digests = frappe.get_all("Email Queue", filters={"message": ["like", "%Leads waiting for a reply%"]}, pluck="name")
		self.assertEqual(len(digests), 1)
		queue = frappe.get_doc("Email Queue", digests[0])
		self.assertIn(OPS, {r.recipient for r in queue.recipients})
		self.assertNotIn(SALES, {r.recipient for r in queue.recipients})
		self.assertIn(overdue.name, queue.message)
		self.assertNotIn(answered.name, queue.message)
		self.assertNotIn(on_time.name, queue.message)

	def _overdue_lead(self, hours_late):
		lead = self._lead()
		frappe.db.set_value(
			"Lead", lead.name, "custom_vellox_first_response_due", add_to_date(now_datetime(), hours=-hours_late)
		)
		return lead

	def test_digest_lists_the_newest_late_leads_and_the_true_count(self):
		from vellox_agency import lead_followup

		frappe.db.set_value("Lead", {"status": ["in", ["Lead", "Open"]]}, "custom_vellox_first_response_due", None)
		oldest, newest = self._overdue_lead(48), self._overdue_lead(1)
		self._overdue_lead(24)
		with unittest.mock.patch.object(lead_followup, "DIGEST_LIMIT", 2):
			lead_followup.send_late_reply_digest()
		queue = frappe.get_doc("Email Queue", {"message": ["like", "%Leads waiting for a reply%"]})
		self.assertIn("Leads waiting for a reply: 3", queue.message)
		self.assertIn(newest.name, queue.message)
		self.assertNotIn(oldest.name, queue.message)

	def test_a_comment_by_the_lead_owner_counts_as_a_reply(self):
		from vellox_agency.lead_followup import overdue_leads

		lead = self._overdue_lead(2)
		frappe.db.set_value("Lead", lead.name, "lead_owner", SALES)
		with self.set_user(SALES):
			frappe.get_doc(
				{
					"doctype": "Comment",
					"comment_type": "Comment",
					"reference_doctype": "Lead",
					"reference_name": lead.name,
					"content": "Called them back.",
				}
			).insert(ignore_permissions=True)
		self.assertNotIn(lead.name, [row.name for row in overdue_leads()])

	def test_no_digest_when_nothing_is_late(self):
		from vellox_agency.lead_followup import send_late_reply_digest

		frappe.db.set_value("Lead", {"status": ["in", ["Lead", "Open"]]}, "custom_vellox_first_response_due", None)
		send_late_reply_digest()
		self.assertFalse(frappe.db.exists("Email Queue", {"message": ["like", "%Leads waiting for a reply%"]}))

	def test_digest_runs_daily(self):
		self.assertIn("vellox_agency.lead_followup.send_late_reply_digest", frappe.get_hooks("scheduler_events")["daily"])


class TestNoShadowedFunctions(FrappeTestCase):
	def test_no_module_defines_the_same_function_twice(self):
		root = Path(frappe.get_app_path("vellox_agency"))
		duplicates = []
		for path in root.rglob("*.py"):
			names = [
				node.name
				for node in ast.parse(path.read_text()).body
				if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
			]
			duplicates += [f"{path.relative_to(root)}:{name}" for name in set(names) if names.count(name) > 1]
		self.assertEqual(sorted(duplicates), [])


class TestRerouteAlertsPatch(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.delivery_setup import setup_delivery_fields

		setup_delivery_fields()

	def _set_recipients(self, name, recipients):
		doc = frappe.get_doc("Notification", name)
		doc.set("recipients", recipients)
		doc.save(ignore_permissions=True)

	def _fields(self, name):
		return [r.receiver_by_document_field for r in frappe.get_doc("Notification", name).recipients]

	def test_old_default_recipients_are_rerouted(self):
		from vellox_agency.patches import route_delivery_alerts_to_team

		for name in ("Vellox Deliverable Client Review", "Vellox Change Request Decision"):
			self._set_recipients(name, [{"receiver_by_document_field": "owner"}])
		route_delivery_alerts_to_team.execute()
		self.assertEqual(self._fields("Vellox Deliverable Client Review"), ["project_manager"])
		self.assertEqual(self._fields("Vellox Change Request Decision"), ["team_emails", "owner"])

	def test_a_condition_an_admin_added_is_left_alone(self):
		from vellox_agency.patches import route_delivery_alerts_to_team

		self._set_recipients(
			"Vellox Deliverable Client Review",
			[{"receiver_by_document_field": "owner", "condition": "doc.deliverable_type == 'Design'"}],
		)
		route_delivery_alerts_to_team.execute()
		self.assertEqual(self._fields("Vellox Deliverable Client Review"), ["owner"])

	def test_existing_projects_get_their_creator_as_manager(self):
		from vellox_agency.patches import backfill_project_managers

		project = frappe.get_doc(
			{"doctype": "Project", "project_name": f"_Test Gaps {frappe.generate_hash(length=8)}", "company": "_Test Company"}
		).insert(ignore_permissions=True)
		project.db_set({"custom_vellox_project_manager": None, "owner": PM})
		kept = frappe.get_doc(
			{"doctype": "Project", "project_name": f"_Test Gaps {frappe.generate_hash(length=8)}", "company": "_Test Company"}
		).insert(ignore_permissions=True)
		kept.db_set("custom_vellox_project_manager", MEMBER)
		backfill_project_managers.execute()
		self.assertEqual(frappe.db.get_value("Project", project.name, "custom_vellox_project_manager"), PM)
		self.assertEqual(frappe.db.get_value("Project", kept.name, "custom_vellox_project_manager"), MEMBER)

	def test_recipients_an_admin_changed_are_left_alone(self):
		from vellox_agency.patches import route_delivery_alerts_to_team

		self._set_recipients("Vellox Deliverable Client Review", [{"receiver_by_role": "Agency Manager"}])
		route_delivery_alerts_to_team.execute()
		self.assertEqual(
			[r.receiver_by_role for r in frappe.get_doc("Notification", "Vellox Deliverable Client Review").recipients],
			["Agency Manager"],
		)
