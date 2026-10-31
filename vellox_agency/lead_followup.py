"""Daily digest of leads still waiting for a first reply (lead-to-project spec section 9, [P3-99])."""

import frappe
from frappe import _
from frappe.utils import format_datetime, get_url_to_form, now_datetime
from frappe.utils.user import get_users_with_role

DIGEST_ROLE = "Vellox Operations"
# Lead statuses that mean nobody has replied yet; any other status counts as answered.
UNANSWERED_STATUSES = ("Lead", "Open")
DIGEST_LIMIT = 200


def overdue_leads() -> list[dict]:
	return frappe.get_all(
		"Lead",
		# Frappe compares an empty datetime as the earliest date, so "is set" is needed
		# to keep leads without a reply deadline out.
		filters=[
			["status", "in", UNANSWERED_STATUSES],
			["custom_vellox_first_response_due", "is", "set"],
			["custom_vellox_first_response_due", "<", now_datetime()],
		],
		fields=["name", "lead_name", "company_name", "lead_owner", "custom_vellox_first_response_due"],
		order_by="custom_vellox_first_response_due asc",
		limit=DIGEST_LIMIT,
	)


def send_late_reply_digest() -> None:
	"""Scheduled daily: one email to Operations listing overdue leads; nothing if none."""
	leads = overdue_leads()
	recipients = get_users_with_role(DIGEST_ROLE)
	if not leads or not recipients:
		return
	esc = frappe.utils.escape_html
	rows = "".join(
		f"<tr><td><a href='{get_url_to_form('Lead', lead.name)}'>{esc(lead.name)}</a></td>"
		f"<td>{esc(lead.lead_name or '')}</td><td>{esc(lead.company_name or '')}</td>"
		f"<td>{esc(lead.lead_owner or _('Unassigned'))}</td>"
		f"<td>{format_datetime(lead.custom_vellox_first_response_due)}</td></tr>"
		for lead in leads
	)
	frappe.sendmail(
		recipients=recipients,
		subject=_("Leads waiting for a reply: {0}").format(len(leads)),
		message=(
			f"<p>{_('These leads passed their first-reply time and nobody has answered yet.')}</p>"
			f"<table><tr><th>{_('Lead')}</th><th>{_('Name')}</th><th>{_('Company')}</th>"
			f"<th>{_('Owner')}</th><th>{_('Reply due')}</th></tr>{rows}</table>"
		),
	)
