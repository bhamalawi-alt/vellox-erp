"""Available hours per person (capacity plan section 3, [P4-30]).

working days    = days - holidays (the Employee's Holiday List, else the
                  Company's) - approved leave, only between the joining and
                  relieving dates
available hours = working days x daily hours
target hours    = available hours x utilization target / 100

Leave follows Frappe HR's own counting: submitted, approved leave only; a half
day takes 0.5 on its half-day date, and several leaves on one date add up to at
most a full day. Holidays include the weekly offs in the Holiday List, so a
site sets its weekend there (Friday and Saturday in Libya). Dates the Holiday
List does not cover are refused rather than counted as working days.

Weeks run Monday to Sunday. Each person's calendar is read once per request,
however many weeks are asked for.
"""

import frappe
from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate

MAX_WEEKS = 104


def _days(start, end):
	day = getdate(start)
	for _offset in range(date_diff(end, start) + 1):
		yield day
		day = add_days(day, 1)


def _person(employee: str) -> frappe._dict:
	person = frappe.db.get_value(
		"Employee",
		employee,
		[
			"date_of_joining",
			"relieving_date",
			"status",
			"custom_vellox_daily_hours as daily_hours",
			"custom_vellox_utilization_target as target",
		],
		as_dict=True,
	)
	if not person:
		frappe.throw(_("Employee {0} not found.").format(employee), frappe.DoesNotExistError)
	return person


def _holidays(employee: str, start, end) -> set:
	holiday_list = get_holiday_list_for_employee(employee, raise_exception=False)
	if not holiday_list:
		frappe.throw(
			_("Set a Holiday List on Employee {0} or its Company to plan their capacity.").format(employee),
			frappe.ValidationError,
		)
	covers = frappe.db.get_value("Holiday List", holiday_list, ["from_date", "to_date"], as_dict=True)
	if getdate(start) < getdate(covers.from_date) or getdate(end) > getdate(covers.to_date):
		frappe.throw(
			_("Holiday List {0} covers {1} to {2}; extend it to plan {3} to {4}.").format(
				holiday_list, covers.from_date, covers.to_date, start, end
			),
			frappe.ValidationError,
		)
	return set(
		frappe.get_all(
			"Holiday",
			filters={"parent": holiday_list, "holiday_date": ["between", [start, end]]},
			pluck="holiday_date",
		)
	)


def _leave_by_day(employee: str, start, end) -> dict:
	"""Days off per date from approved, submitted leave, capped at one day."""
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
		half_day = getdate(row.half_day_date) if row.half_day and row.half_day_date else None
		for day in _days(max(getdate(row.from_date), getdate(start)), min(getdate(row.to_date), getdate(end))):
			leave[day] = min(1, leave.get(day, 0) + (0.5 if day == half_day else 1))
	return leave


def _working_days_by_date(employee: str, start, end) -> tuple[dict, frappe._dict]:
	"""Working-day share (0, 0.5 or 1) for every date in the range, plus the Employee."""
	person = _person(employee)
	days = {day: 0 for day in _days(start, end)}
	if person.status == "Left" and not person.relieving_date:
		return days, person  # left, date unknown: no capacity
	first = max(getdate(start), getdate(person.date_of_joining)) if person.date_of_joining else getdate(start)
	last = min(getdate(end), getdate(person.relieving_date)) if person.relieving_date else getdate(end)
	if first > last:
		return days, person
	holidays = _holidays(employee, first, last)
	leave = _leave_by_day(employee, first, last)
	for day in _days(first, last):
		if day not in holidays:
			days[day] = 1 - leave.get(day, 0)
	return days, person


def working_days(employee: str, start, end) -> float:
	days, _person_row = _working_days_by_date(employee, start, end)
	return sum(days.values())


def available_hours(employee: str, start, end) -> float:
	days, person = _working_days_by_date(employee, start, end)
	return sum(days.values()) * flt(person.daily_hours)


def weekly_capacity(employee: str, from_day, weeks: int) -> list[dict]:
	"""Capacity for `weeks` Monday-to-Sunday weeks, starting with the week of from_day."""
	if not 0 < weeks <= MAX_WEEKS:
		frappe.throw(_("Plan between 1 and {0} weeks at a time.").format(MAX_WEEKS), frappe.ValidationError)
	day = getdate(from_day)
	first = add_days(day, -day.weekday())
	days, person = _working_days_by_date(employee, first, add_days(first, 7 * weeks - 1))
	result = []
	for n in range(weeks):
		week_start = add_days(first, 7 * n)
		working = sum(days[d] for d in _days(week_start, add_days(week_start, 6)))
		hours = working * flt(person.daily_hours)
		result.append(
			{
				"week_start": week_start,
				"working_days": working,
				"available_hours": hours,
				"target_hours": hours * flt(person.target) / 100,
			}
		)
	return result


def week_capacity(employee: str, any_day) -> dict:
	"""Capacity for the Monday-to-Sunday week that contains any_day."""
	return weekly_capacity(employee, any_day, 1)[0]
