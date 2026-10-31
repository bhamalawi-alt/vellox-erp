"""Send client-review alerts to the project manager and Change Request decisions
to the project team ([P3-99]).

setup_notification_fixtures leaves existing records alone so admin edits survive
migrate; this rewrites the recipients only where they are still the old default.
"""

import frappe

from vellox_agency.delivery_setup import REROUTED_NOTIFICATIONS


def _recipients(doc) -> list[dict]:
	return [
		{k: v for k, v in {"receiver_by_document_field": r.receiver_by_document_field, "receiver_by_role": r.receiver_by_role}.items() if v}
		for r in doc.recipients
	]


def execute():
	for name, (old, new) in REROUTED_NOTIFICATIONS.items():
		if not frappe.db.exists("Notification", name):
			continue
		doc = frappe.get_doc("Notification", name)
		if _recipients(doc) == old:
			doc.set("recipients", new)
			doc.save(ignore_permissions=True)
