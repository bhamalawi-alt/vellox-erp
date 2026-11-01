"""A confirmed booking of a person on a project (capacity plan section 2, [P4-32])."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class VelloxResourceAllocation(Document):
	def validate(self):
		if getdate(self.to_date) < getdate(self.from_date):
			frappe.throw(_("The booking must end on or after its start date."), frappe.ValidationError)
		if flt(self.hours_per_week) <= 0:
			frappe.throw(_("Hours per week must be more than zero."), frappe.ValidationError)
		if self.task and frappe.db.get_value("Task", self.task, "project") != self.project:
			frappe.throw(_("Task {0} is not part of project {1}.").format(self.task, self.project), frappe.ValidationError)

	def on_submit(self):
		from vellox_agency.capacity import warn_if_overbooked

		warn_if_overbooked(self.employee, self.from_date, self.to_date)
