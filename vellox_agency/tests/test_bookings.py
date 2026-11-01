"""Bookings, overbooking and the likely line ([P4-32], plan sections 2, 3 and 7).

Follows the plan's worked example (section 8) on the test calendar: Developer
"Sara", week of Mon 9 Nov 2026 (Fri/Sat weekend and a Wednesday holiday, so 4
working days), one day of leave -> 3 days, 24 h available, 18 h target; booked
30 h + 8 h = 38 h, so overbooked by 14 h.
"""

from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from vellox_agency.security import JOB_PROFILES

WEEK = "2026-11-09"
PM = "bk-pm@example.com"
TEAM = "bk-team@example.com"


@contextmanager
def _as_job(*jobs):
	with patch("vellox_agency.security._job_roles", return_value=set(jobs)):
		yield


def _user(email, roles):
	# Real profiles, never Sales or Agency Manager (they join lead routing on the test site).
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": "BK", "send_welcome_email": 0}).insert(
			ignore_permissions=True
		)
		frappe.get_doc("User", email).add_roles(*roles)
	return email


class _BookingCase(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.security import setup_roles_and_permissions
		from vellox_agency.tests.test_capacity import LEAVE_TYPE, _employee, setup_calendar_fixtures

		setup_calendar_fixtures()  # holiday list, leave types, Gender, HR settings
		frappe.reload_doctype("Vellox Resource Allocation")
		setup_roles_and_permissions()
		cls.leave_type = LEAVE_TYPE
		_user(PM, JOB_PROFILES["Project Manager"])
		_user(TEAM, JOB_PROFILES["Team Member"])
		cls.sara = _employee("Sara Booked").name
		cls.other = _employee("Omar Booked").name
		frappe.db.set_value("Employee", cls.other, "user_id", TEAM)
		cls.project = cls._project("Web build")
		cls.second = cls._project("Other work")

	@classmethod
	def _project(cls, title):
		return frappe.get_doc(
			{"doctype": "Project", "project_name": f"_Test BK {title} {frappe.generate_hash(length=5)}", "company": "_Test Company"}
		).insert(ignore_permissions=True).name

	def _book(self, employee, project, hours, from_date="2026-11-09", to_date="2026-11-15", submit=True):
		booking = frappe.get_doc(
			{
				"doctype": "Vellox Resource Allocation",
				"employee": employee,
				"project": project,
				"from_date": from_date,
				"to_date": to_date,
				"hours_per_week": hours,
			}
		).insert(ignore_permissions=True)
		if submit:
			booking.submit()
		return booking

	def _fresh(self, name):
		# Bookings persist until the class ends, so each test books its own people.
		from vellox_agency.tests.test_capacity import _employee

		return _employee(f"{name} {frappe.generate_hash(length=4)}").name

	def _week(self, employee):
		from vellox_agency.capacity import week_capacity

		return week_capacity(employee, WEEK)


class TestBookings(_BookingCase):
	def test_the_plans_worked_example(self):
		sara = self._fresh("Sara")
		leave = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": sara,
				"leave_type": self.leave_type,
				"from_date": "2026-11-10",
				"to_date": "2026-11-10",
				"status": "Approved",
				"company": "_Test Company",
			}
		).insert(ignore_permissions=True)
		leave.submit()
		self._book(sara, self.project, 30)
		self._book(sara, self.second, 8)
		week = self._week(sara)
		self.assertEqual(
			(week["available_hours"], week["target_hours"], week["confirmed_hours"], week["free_hours"], week["overbooked_hours"]),
			(24, 18, 38, 0, 14),
		)

	def test_free_hours_without_overbooking(self):
		person = self._fresh("Free")
		self._book(person, self.project, 20)
		week = self._week(person)
		self.assertEqual((week["confirmed_hours"], week["free_hours"], week["overbooked_hours"]), (20, 12, 0))

	def test_only_confirmed_bookings_count(self):
		person = self._fresh("Draft")
		self._book(person, self.second, 10, submit=False)
		self._book(person, self.second, 10).cancel()
		self.assertEqual(self._week(person)["confirmed_hours"], 0)

	def test_a_part_week_booking_counts_its_share(self):
		# Wed 11 to Sun 15: 5 of the week's 7 days.
		person = self._fresh("Part")
		self._book(person, self.project, 14, from_date="2026-11-11", to_date="2026-11-15")
		self.assertEqual(self._week(person)["confirmed_hours"], 10)

	def test_a_booking_needs_sane_dates_and_hours(self):
		for kwargs in ({"from_date": "2026-11-15", "to_date": "2026-11-09"}, {"hours": 0}):
			with self.subTest(kwargs=kwargs), self.assertRaises(frappe.ValidationError):
				args = {"hours": 10, **kwargs}
				self._book(self.other, self.project, args.pop("hours"), submit=False, **args)

	def test_a_task_must_belong_to_the_booked_project(self):
		task = frappe.get_doc({"doctype": "Task", "subject": "BK task", "project": self.second}).insert(
			ignore_permissions=True
		)
		booking = frappe.get_doc(
			{
				"doctype": "Vellox Resource Allocation",
				"employee": self.other,
				"project": self.project,
				"task": task.name,
				"from_date": "2026-11-09",
				"to_date": "2026-11-15",
				"hours_per_week": 5,
			}
		)
		with self.assertRaises(frappe.ValidationError):
			booking.insert(ignore_permissions=True)

	def test_overbooking_warns_but_does_not_block(self):
		person = self._fresh("Busy")
		self._book(person, self.project, 30)
		frappe.clear_messages()
		booking = self._book(person, self.second, 8)
		self.assertEqual(booking.docstatus, 1)
		messages = " ".join(str(m) for m in frappe.get_message_log())
		self.assertIn("overbooked", messages.lower())


class TestLikelyDemand(_BookingCase):
	def test_open_deals_add_likely_hours_by_role(self):
		from vellox_agency.capacity import likely_demand
		from vellox_agency.setup.commercial import setup_commercial_foundation
		from vellox_agency.setup.practice_templates import setup_practice_templates
		from vellox_agency.tests.test_pipeline import _make_opportunity, _make_qualified_lead

		setup_commercial_foundation()
		setup_practice_templates()
		item = frappe.db.get_value("Item", {"custom_vellox_project_template": "Vellox — Web Development"})
		opp = _make_opportunity(
			_make_qualified_lead().name, expected_closing="2026-11-09", items=[{"item_code": item, "qty": 1, "rate": 1000}]
		)
		opp.db_set("custom_vellox_probability", 60)
		# Web Development: Developer 30 of 45 template days -> 240 h x 60 % over 9 weeks = 16 h a week.
		demand = likely_demand(WEEK, 10)
		self.assertAlmostEqual(demand["Developer"][0]["likely_hours"], 16, places=2)
		self.assertAlmostEqual(demand["Developer"][8]["likely_hours"], 16, places=2)
		self.assertAlmostEqual(demand["Developer"][9]["likely_hours"], 0, places=2)

	def test_lost_deals_add_nothing(self):
		from vellox_agency.capacity import likely_demand
		from vellox_agency.tests.test_pipeline import _make_opportunity, _make_qualified_lead

		before = likely_demand(WEEK, 2)
		item = frappe.db.get_value("Item", {"custom_vellox_project_template": "Vellox — Web Development"})
		opp = _make_opportunity(
			_make_qualified_lead().name, expected_closing="2026-11-09", items=[{"item_code": item, "qty": 1, "rate": 1000}]
		)
		opp.db_set({"custom_vellox_probability": 60, "status": "Lost"})
		self.assertEqual(likely_demand(WEEK, 2), before)


class TestBookingAccess(_BookingCase):
	def test_team_members_see_only_their_own_bookings(self):
		mine = self._book(self.other, self.project, 5)
		theirs = self._book(self.sara, self.project, 5)
		with self.set_user(TEAM):
			self.assertTrue(frappe.has_permission("Vellox Resource Allocation", "read", doc=mine))
			self.assertFalse(frappe.has_permission("Vellox Resource Allocation", "read", doc=theirs))
			names = frappe.get_list("Vellox Resource Allocation", pluck="name")
		self.assertIn(mine.name, names)
		self.assertNotIn(theirs.name, names)

	def test_sales_sees_no_bookings(self):
		from vellox_agency.security import NONE, access_level

		with _as_job("Vellox Sales"):
			self.assertEqual(access_level("Vellox Resource Allocation", "someone@example.com"), NONE)

	def test_project_managers_book_people(self):
		with self.set_user(PM):
			self.assertTrue(frappe.has_permission("Vellox Resource Allocation", "submit"))


class TestTeamCapacityReport(_BookingCase):
	REPORT = "Vellox Team Capacity"

	def _run(self, user, weeks=1):
		from vellox_agency.vellox_agency_projects.report.vellox_team_capacity.vellox_team_capacity import (
			execute,
		)

		with self.set_user(user):
			_columns, rows = execute(frappe._dict(from_date=WEEK, weeks=weeks))
		return rows

	def test_managers_see_each_person_and_week(self):
		from vellox_agency.tests.test_capacity import _employee

		person = _employee(f"Report {frappe.generate_hash(length=4)}").name
		self._book(person, self.project, 20)
		rows = [r for r in self._run(PM) if r.get("employee") == person]
		self.assertEqual(len(rows), 1)
		self.assertEqual(getdate(rows[0]["week_start"]), getdate(WEEK))
		self.assertEqual((rows[0]["available_hours"], rows[0]["confirmed_hours"]), (32, 20))

	def test_team_members_see_only_themselves_and_no_likely_line(self):
		rows = self._run(TEAM)
		self.assertIn(self.other, {r.get("employee") for r in rows})
		own = set(frappe.get_all("Employee", filters={"user_id": TEAM}, pluck="name"))
		self.assertTrue({r.get("employee") for r in rows} <= own, "only their own rows, no likely line")

	def test_the_report_follows_booking_access(self):
		from vellox_agency.report_guard import can_run_report

		self.assertTrue(can_run_report(self.REPORT, PM))
		self.assertTrue(can_run_report(self.REPORT, TEAM))  # the report shows them only their own rows
		with _as_job("Vellox Sales"):
			self.assertFalse(can_run_report(self.REPORT, "someone@example.com"))
