"""Daily jobs and their once-a-day guard ([P3-100]).

Frappe logs every scheduled run in Scheduled Job Log. Jobs never commit: the
scheduler commits after a job succeeds and rolls back if it fails.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_to_date, format_date, get_url_to_form, now_datetime, nowdate

from vellox_agency.pipeline import CLOSED_STATUSES, STALE_DAYS

DAILY_GUARD_KEY = "vellox_daily"


def first_run_today(job: str) -> bool:
	"""True the first time `job` asks today, so a re-run (a retried or manually
	triggered job) does not send the same emails twice."""
	cache = frappe.cache()
	key = cache.make_key(f"{DAILY_GUARD_KEY}:{job}:{nowdate()}")
	return bool(cache.set(key, 1, ex=2 * 24 * 3600, nx=True))


def reset_daily_guards() -> None:
	frappe.cache().delete_keys(DAILY_GUARD_KEY)


def _stale_opportunities_by_owner() -> dict[str, list[dict]]:
	rows = frappe.get_all(
		"Opportunity",
		filters={
			"modified": ("<", add_to_date(now_datetime(), days=-STALE_DAYS)),
			"status": ("not in", CLOSED_STATUSES),
		},
		fields=["name", "title", "party_name", "sales_stage", "opportunity_owner", "owner", "modified"],
		order_by="modified asc",
	)
	enabled = set(frappe.get_all("User", filters={"enabled": 1, "user_type": "System User"}, pluck="name"))
	by_owner = defaultdict(list)
	for row in rows:
		owner = row.opportunity_owner or row.owner
		if owner in enabled and owner != "Administrator":
			by_owner[owner].append(row)
	return by_owner


def send_stale_opportunity_reminders() -> None:
	"""Daily: each owner gets one list of their open opportunities with no update in STALE_DAYS."""
	if not first_run_today("stale_opportunities"):
		return
	esc = frappe.utils.escape_html
	for owner, rows in _stale_opportunities_by_owner().items():
		items = "".join(
			f"<tr><td><a href='{get_url_to_form('Opportunity', row.name)}'>{esc(row.name)}</a></td>"
			f"<td>{esc(row.title or row.party_name or '')}</td><td>{esc(row.sales_stage or '')}</td>"
			f"<td>{format_date(row.modified)}</td></tr>"
			for row in rows
		)
		frappe.sendmail(
			recipients=[owner],
			subject=_("Opportunities with no update for {0} days: {1}").format(STALE_DAYS, len(rows)),
			message=(
				f"<p>{_('These open opportunities have not been updated recently. Follow up, or mark them Lost.')}</p>"
				f"<table><tr><th>{_('Opportunity')}</th><th>{_('Client')}</th><th>{_('Stage')}</th>"
				f"<th>{_('Last update')}</th></tr>{items}</table>"
			),
		)
