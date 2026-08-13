# Copyright (c) 2026, Vellox Team and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AgencyInvoice(Document):
	def validate(self):
		self.set_totals()
		self.set_invoice_number()

	def set_totals(self):
		subtotal = 0.0
		for line in self.invoice_lines:
			line.amount = (line.quantity or 0) * (line.rate or 0)
			subtotal += line.amount
		self.subtotal = subtotal
		self.total = (self.subtotal or 0) + (self.tax or 0)

	def set_invoice_number(self):
		if not self.invoice_number and self.name:
			self.invoice_number = self.name
