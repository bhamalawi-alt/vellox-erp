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

Bookings ([P4-32]): confirmed hours = submitted Vellox Resource Allocations,
each spread evenly over its calendar days (hours per week / 7 a day), so a part
week counts its share. free = available - confirmed (never below 0);
overbooked = confirmed - available when positive. Overbooking warns, it does
not block.

Likely demand (section 3): open Opportunities' service items -> practice
template steps -> hours per role (est_days x 8) x win probability, spread
evenly over the template's duration from the expected close date. It is a
separate line by role and never counts as overbooking.

Weeks run Monday to Sunday. Each person's calendar is read once per request,
however many weeks are asked for.
"""

import math

import frappe
from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate

MAX_WEEKS = 104
HOURS_PER_TEMPLATE_DAY = 8
WORKING_DAYS_PER_WEEK = 5


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


def _booked_by_date(employee: str, start, end) -> dict:
	"""Confirmed booking hours per calendar day from submitted allocations."""
	booked = {}
	for row in frappe.get_all(
		"Vellox Resource Allocation",
		filters={"employee": employee, "docstatus": 1, "from_date": ["<=", end], "to_date": [">=", start]},
		fields=["from_date", "to_date", "hours_per_week"],
	):
		per_day = flt(row.hours_per_week) / 7
		for day in _days(max(getdate(row.from_date), getdate(start)), min(getdate(row.to_date), getdate(end))):
			booked[day] = booked.get(day, 0) + per_day
	return booked


def _first_monday(from_day):
	day = getdate(from_day)
	return add_days(day, -day.weekday())


def _check_weeks(weeks: int) -> None:
	if not 0 < weeks <= MAX_WEEKS:
		frappe.throw(_("Plan between 1 and {0} weeks at a time.").format(MAX_WEEKS), frappe.ValidationError)


def weekly_capacity(employee: str, from_day, weeks: int) -> list[dict]:
	"""Capacity for `weeks` Monday-to-Sunday weeks, starting with the week of from_day."""
	_check_weeks(weeks)
	first = _first_monday(from_day)
	last = add_days(first, 7 * weeks - 1)
	days, person = _working_days_by_date(employee, first, last)
	booked = _booked_by_date(employee, first, last)
	result = []
	for n in range(weeks):
		week_start = add_days(first, 7 * n)
		week = list(_days(week_start, add_days(week_start, 6)))
		working = sum(days[d] for d in week)
		hours = working * flt(person.daily_hours)
		confirmed = round(sum(booked.get(d, 0) for d in week), 2)
		result.append(
			{
				"week_start": week_start,
				"working_days": working,
				"available_hours": hours,
				"target_hours": hours * flt(person.target) / 100,
				"confirmed_hours": confirmed,
				"free_hours": max(0, round(hours - confirmed, 2)),
				"overbooked_hours": max(0, round(confirmed - hours, 2)),
			}
		)
	return result


def warn_if_overbooked(employee: str, from_date, to_date) -> None:
	"""After a booking is submitted: say which weeks are now overbooked (does not block)."""
	first = _first_monday(from_date)
	weeks = min(MAX_WEEKS, math.ceil((date_diff(to_date, first) + 1) / 7))
	try:
		rows = weekly_capacity(employee, first, weeks)
	except frappe.ValidationError as error:
		frappe.msgprint(_("Could not check for overbooking: {0}").format(error), indicator="orange")
		return
	over = [row for row in rows if row["overbooked_hours"] > 0]
	if over:
		weeks_text = ", ".join(f"{row['week_start']} (+{row['overbooked_hours']} h)" for row in over)
		frappe.msgprint(
			_("{0} is overbooked in the week(s) starting {1}.").format(employee, weeks_text),
			title=_("Overbooked"),
			indicator="orange",
		)


def likely_demand(from_day, weeks: int) -> dict[str, list[dict]]:
	"""Likely hours per role and week from open opportunities (never confirmed demand)."""
	from vellox_agency.pipeline import CLOSED_STATUSES
	from vellox_agency.setup.practice_templates import get_steps

	_check_weeks(weeks)
	first = _first_monday(from_day)
	week_starts = [add_days(first, 7 * n) for n in range(weeks)]
	demand: dict[str, list[float]] = {}
	opportunities = frappe.get_all(
		"Opportunity",
		filters={"status": ["not in", CLOSED_STATUSES], "expected_closing": ["is", "set"]},
		fields=["name", "expected_closing", "custom_vellox_probability as probability"],
	)
	if not opportunities:
		return {}
	items = frappe.get_all(
		"Opportunity Item",
		filters={"parent": ["in", [o.name for o in opportunities]], "parenttype": "Opportunity"},
		fields=["parent", "item_code"],
	)
	templates = dict(
		frappe.get_all(
			"Item",
			filters={"name": ["in", list({i.item_code for i in items})]},
			fields=["name", "custom_vellox_project_template"],
			as_list=True,
		)
	)
	steps_by_template = {}
	for opp in opportunities:
		probability = flt(opp.probability) / 100
		if not probability:
			continue
		for item in (i for i in items if i.parent == opp.name):
			template = templates.get(item.item_code)
			if not template:
				continue
			steps = steps_by_template.setdefault(template, get_steps(template))
			total_days = sum(flt(s.est_days) for s in steps)
			if not total_days:
				continue
			duration_weeks = math.ceil(total_days / WORKING_DAYS_PER_WEEK)
			start = _first_monday(opp.expected_closing)
			role_hours = {}
			for step in steps:
				role_hours[step.default_role] = role_hours.get(step.default_role, 0) + flt(step.est_days) * HOURS_PER_TEMPLATE_DAY
			for role, hours in role_hours.items():
				per_week = hours * probability / duration_weeks
				row = demand.setdefault(role, [0.0] * weeks)
				for n, week_start in enumerate(week_starts):
					offset = date_diff(week_start, start) // 7
					if 0 <= offset < duration_weeks:
						row[n] += per_week
	return {
		role: [{"week_start": w, "likely_hours": round(h, 2)} for w, h in zip(week_starts, hours, strict=True)]
		for role, hours in demand.items()
	}


def week_capacity(employee: str, any_day) -> dict:
	"""Capacity for the Monday-to-Sunday week that contains any_day."""
	return weekly_capacity(employee, any_day, 1)[0]
