"""Change Requests saved with the old blank status become Draft ([P3-146]).

The blank option was removed and status made required; without this, such rows
stay blank (and outside the Draft filter) until their next save.
"""

import frappe


def execute():
	request = frappe.qb.DocType("Vellox Change Request")
	(
		frappe.qb.update(request)
		.set(request.status, "Draft")
		.where(request.status.isnull() | (request.status == ""))
		.run()
	)
