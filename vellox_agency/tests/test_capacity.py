"""Available hours per person ([P4-30], capacity plan section 3).

Sample week: Monday 9 to Sunday 15 November 2026. The Holiday List has the
Friday/Saturday weekend (13, 14) and a public holiday on Wednesday 11, so the
working days are Mon 9, Tue 10, Thu 12 and Sun 15.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

WEEK = ("2026-11-09", "2026-11-15")
HOLIDAY_LIST = "_Test Vellox Holidays 2026"
LEAVE_TYPE = "_Test Vellox Unpaid Leave"


def _holiday_list():
	if frappe.db.exists("Holiday List", HOLIDAY_LIST):
		return HOLIDAY_LIST
	holidays = [{"holiday_date": "2026-11-11", "description": "Public holiday"}]
	holidays += [{"holiday_date": d, "description": "Weekend", "weekly_off": 1} for d in ("2026-11-06", "2026-11-07", "2026-11-13", "2026-11-14", "2026-11-20", "2026-11-21")]
	frappe.get_doc(
		{"doctype": "Holiday List", "holiday_list_name": HOLIDAY_LIST, "from_date": "2026-01-01", "to_date": "2026-12-31", "holidays": holidays}
	).insert(ignore_permissions=True)
	return HOLIDAY_LIST


def _employee(name, **kw):
	return frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": name,
			"gender": "Female",
			"date_of_birth": "1990-01-01",
			"date_of_joining": "2025-01-01",
			"company": "_Test Company",
			"status": "Active",
			"holiday_list": _holiday_list(),
			**kw,
		}
	).insert(ignore_permissions=True)


class TestCapacity(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from vellox_agency.setup.people import setup_people_fields
		from vellox_agency.tests.test_offer_builder import _bootstrap_erpnext_test_fixtures

		_bootstrap_erpnext_test_fixtures()
		setup_people_fields()
		frappe.db.set_single_value("HR Settings", "leave_approver_mandatory_in_leave_application", 0)
		# The setup wizard normally creates Gender records; test sites may lack them.
		if not frappe.db.exists("Gender", "Female"):
			frappe.get_doc({"doctype": "Gender", "gender": "Female"}).insert(ignore_permissions=True)
		if not frappe.db.exists("Leave Type", LEAVE_TYPE):
			frappe.get_doc({"doctype": "Leave Type", "leave_type_name": LEAVE_TYPE, "is_lwp": 1}).insert(
				ignore_permissions=True
			)

	def _leave(self, employee, from_date, to_date, half_day=0, status="Approved", submit=True):
		leave = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": employee.name,
				"leave_type": LEAVE_TYPE,
				"from_date": from_date,
				"to_date": to_date,
				"half_day": half_day,
				"half_day_date": from_date if half_day else None,
				"status": status,
				"company": "_Test Company",
			}
		).insert(ignore_permissions=True)
		if submit:
			leave.submit()
		return leave

	def _hours(self, employee):
		from vellox_agency.capacity import available_hours

		return available_hours(employee.name, *WEEK)

	def test_staff_records_carry_hours_target_and_seniority(self):
		meta = frappe.get_meta("Employee")
		self.assertEqual(meta.get_field("custom_vellox_daily_hours").default, "8")
		self.assertEqual(meta.get_field("custom_vellox_utilization_target").default, "75")
		self.assertEqual(meta.get_field("custom_vellox_seniority").options.split("\n"), ["", "Junior", "Mid", "Senior"])
		self.assertTrue(frappe.db.exists("Employment Type", "Contract"), "freelancers are Contract employees")

	def test_a_week_without_leave(self):
		from vellox_agency.capacity import week_capacity

		employee = _employee("Cap Full")
		self.assertEqual(self._hours(employee), 32)  # 4 working days x 8 h
		week = week_capacity(employee.name, WEEK[0])
		self.assertEqual((week["working_days"], week["available_hours"], week["target_hours"]), (4, 32, 24))

	def test_approved_leave_is_taken_off(self):
		employee = _employee("Cap Leave")
		self._leave(employee, "2026-11-10", "2026-11-10")
		self.assertEqual(self._hours(employee), 24)

	def test_half_day_leave_takes_half_a_day(self):
		employee = _employee("Cap Half")
		self._leave(employee, "2026-11-12", "2026-11-12", half_day=1)
		self.assertEqual(self._hours(employee), 28)

	def test_leave_that_is_not_approved_does_not_count(self):
		employee = _employee("Cap Open")
		self._leave(employee, "2026-11-10", "2026-11-10", status="Open", submit=False)
		self.assertEqual(self._hours(employee), 32)

	def test_leave_over_a_holiday_is_not_taken_off_twice(self):
		employee = _employee("Cap Span")
		self._leave(employee, "2026-11-10", "2026-11-12")  # Tue-Thu, Wed is the public holiday
		self.assertEqual(self._hours(employee), 16)  # Mon and Sun left

	def test_only_days_between_joining_and_leaving_count(self):
		joiner = _employee("Cap Joiner", date_of_joining="2026-11-12")
		self.assertEqual(self._hours(joiner), 16)  # Thu and Sun
		leaver = _employee("Cap Leaver", relieving_date="2026-11-10", status="Left")
		self.assertEqual(self._hours(leaver), 16)  # Mon and Tue

	def test_a_freelancer_uses_their_own_daily_hours(self):
		freelancer = _employee("Cap Freelancer", employment_type="Contract", custom_vellox_daily_hours=4)
		self.assertEqual(self._hours(freelancer), 16)

	def test_a_person_without_a_holiday_list_gets_a_clear_error(self):
		from unittest.mock import patch

		from vellox_agency.capacity import available_hours

		employee = _employee("Cap NoList")
		# Neither the employee nor the company has a Holiday List.
		with patch("vellox_agency.capacity.get_holiday_list_for_employee", return_value=None):
			with self.assertRaisesRegex(frappe.ValidationError, "Holiday List"):
				available_hours(employee.name, *WEEK)

	def test_weeks_are_listed_monday_to_sunday(self):
		from vellox_agency.capacity import weekly_capacity

		employee = _employee("Cap Weeks")
		weeks = weekly_capacity(employee.name, "2026-11-11", 2)  # a Wednesday
		self.assertEqual([w["week_start"] for w in weeks], [getdate("2026-11-09"), getdate("2026-11-16")])
		self.assertEqual(weeks[0]["available_hours"], 32)

