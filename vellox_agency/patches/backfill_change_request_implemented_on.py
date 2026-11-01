"""Fill Implemented On for change requests implemented before [P4-35].

Project profit counts a Closed request only if it was implemented first; a
request closed straight from Approved was withdrawn. Requests now Implemented
get the date too. The date comes from the request's change history (the
doctype tracks changes). A request still Implemented with no history left gets
the date of its last change; a Closed one with no history stays blank, as it
cannot be told apart from a withdrawn one.
"""

import json

import frappe
from frappe.utils import getdate


def execute():
	names = frappe.get_all(
		"Vellox Change Request",
		filters={"status": ["in", ("Implemented", "Closed")], "implemented_on": ["is", "not set"]},
		fields=["name", "status", "modified"],
	)
	if not names:
		return
	implemented = {}
	for version in frappe.get_all(
		"Version",
		filters={"ref_doctype": "Vellox Change Request", "docname": ["in", [n.name for n in names]]},
		fields=["docname", "data", "creation"],
		order_by="creation asc",
	):
		try:
			changed = json.loads(version.data or "{}").get("changed") or []
		except ValueError:
			continue
		if any(row[0] == "status" and row[2] == "Implemented" for row in changed if len(row) == 3):
			implemented.setdefault(version.docname, getdate(version.creation))
	for request in names:
		day = implemented.get(request.name)
		if not day and request.status == "Implemented":
			day = getdate(request.modified)
		if day:
			frappe.db.set_value(
				"Vellox Change Request", request.name, "implemented_on", day, update_modified=False
			)
