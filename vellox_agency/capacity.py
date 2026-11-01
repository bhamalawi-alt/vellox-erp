"""Available hours per person (capacity plan section 3, [P4-30]).

working days    = days - holidays (the Employee's Holiday List, else the
                  Company's) - approved leave (half-day leave counts 0.5),
                  only between the joining and relieving dates
available hours = working days x daily hours
target hours    = available hours x utilization target / 100

Weeks run Monday to Sunday. Holidays include the weekly offs in the Holiday
List, so a site sets its weekend there (Friday and Saturday in Libya).
"""

import frappe
from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate

from vellox_agency.setup.people import DEFAULT_DAILY_HOURS, DEFAULT_UTILIZATION_TARGET


def _days(start, end):
	day = getdate(start)
	for _offset in range(date_diff(end, start) + 1):
		yield day
		day = add_days(day, 1)


def _holidays(holiday_list: str, start, end) -> set:
	return set(
		frappe.get_all(
			"Holiday",
			filters={"parent": holiday_list, "holiday_date": ["between", [start, end]]},
			pluck="holiday_date",
		)
	)


def _leave_by_day(employee: str, start, end) -> dict:
	"""Approved, submitted leave per day: 1 for a full day, 0.5 for a half day."""
	leave = {}
	for row in frappe.get_all(
		"Leave Application",
		filters={
			"employee": employee,
			"docstatus": 1,
			"status": "Approved",
			"from_date": ["<=", end],
			"to_date": [">=", start],
		},
		fields=["from_date", "to_date", "half_day", "half_day_date"],
	):
		for day in _days(max(getdate(row.from_date), getdate(start)), min(getdate(row.to_date), getdate(end))):
			half = row.half_day and (getdate(row.half_day_date or row.from_date) == day)
			leave[day] = max(leave.get(day, 0), 0.5 if half else 1)
	return leave


def working_days(employee: str, start, end) -> float:
	person = frappe.db.get_value(
		"Employee", employee, ["date_of_joining", "relieving_date"], as_dict=True
	)
	holiday_list = get_holiday_list_for_employee(employee, raise_exception=False)
	if not holiday_list:
		frappe.throw(
			_("Set a Holiday List on Employee {0} or its Company to plan their capacity.").format(employee),
			frappe.ValidationError,
		)
	first = max(getdate(start), getdate(person.date_of_joining)) if person.date_of_joining else getdate(start)
	last = min(getdate(end), getdate(person.relieving_date)) if person.relieving_date else getdate(end)
	if first > last:
		return 0
	holidays = _holidays(holiday_list, first, last)
	leave = _leave_by_day(employee, first, last)
	return sum(1 - leave.get(day, 0) for day in _days(first, last) if day not in holidays)


def available_hours(employee: str, start, end) -> float:
	daily = frappe.db.get_value("Employee", employee, "custom_vellox_daily_hours")
	hours = DEFAULT_DAILY_HOURS if daily is None else flt(daily)
	return working_days(employee, start, end) * hours


def week_capacity(employee: str, any_day) -> dict:
	"""Capacity for the Monday-to-Sunday week that contains any_day."""
	day = getdate(any_day)
	week_start = add_days(day, -day.weekday())
	week_end = add_days(week_start, 6)
	target = frappe.db.get_value("Employee", employee, "custom_vellox_utilization_target")
	target = DEFAULT_UTILIZATION_TARGET if target is None else flt(target)
	days = working_days(employee, week_start, week_end)
	hours = available_hours(employee, week_start, week_end)
	return {
		"week_start": week_start,
		"working_days": days,
		"available_hours": hours,
		"target_hours": hours * target / 100,
	}


def weekly_capacity(employee: str, from_day, weeks: int) -> list[dict]:
	day = getdate(from_day)
	first = add_days(day, -day.weekday())
	return [week_capacity(employee, add_days(first, 7 * n)) for n in range(weeks)]
