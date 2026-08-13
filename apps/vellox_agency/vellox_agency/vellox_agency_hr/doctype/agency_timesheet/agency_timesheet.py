# Copyright (c) 2026, Vellox Team and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class AgencyTimesheet(Document):
	def validate(self):
		self.set_totals()

	def set_totals(self):
		total = 0.0
		billable = 0.0
		for entry in self.timesheet_entries:
			hours = entry.hours or 0
			total += hours
			if entry.billable:
				billable += hours
		self.total_hours = total
		self.billable_hours = billable
