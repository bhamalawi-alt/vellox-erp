"""Secured website inquiry intake — design section 2 of the approved
Lead-to-Project specification ([P2-16]/[P2-17]).

Guests can reach ONLY this endpoint. Submissions are validated, rate-limited
per IP, deduplicated against open Leads from the last 24 hours, and stored on
standard Lead records with consent metadata.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, validate_email_address

from vellox_agency.setup.commercial import PRACTICES

MAX_PER_HOUR = 5
DEDUP_WINDOW_HOURS = 24
RATE_LIMIT_KEY = "vellox_intake"


def _client_ip() -> str:
	return getattr(frappe.local, "client_ip", None) or "0.0.0.0"


def _rate_limit_key(ip: str | None = None):
	cache = frappe.cache()
	return cache, cache.make_key(f"{RATE_LIMIT_KEY}:{ip or _client_ip()}")


def reset_rate_limit(ip: str | None = None) -> None:
	cache, key = _rate_limit_key(ip)
	cache.delete_value(key, make_keys=False)


def _rate_limit() -> None:
	cache, key = _rate_limit_key()
	count = cache.incr(key)
	if count == 1:
		cache.expire(key, 3600)
	if cint(count) > MAX_PER_HOUR:
		frappe.throw(
			_("Too many inquiries from your network. Please try again later."),
			frappe.exceptions.TooManyRequestsError,
		)


def _validate_payload(full_name, email, services, message, consent):
	if not full_name or not (2 <= len(full_name.strip()) <= 140):
		frappe.throw(_("Please provide your name."), frappe.ValidationError)
	if not email or not validate_email_address(email):
		frappe.throw(_("Please provide a valid email address."), frappe.ValidationError)
	if isinstance(services, str):
		try:
			services = json.loads(services)
		except ValueError:
			services = []
	valid_codes = {p["item_code"] for p in PRACTICES}
	if not services or not set(services).issubset(valid_codes):
		frappe.throw(_("Please select at least one valid Vellox service."), frappe.ValidationError)
	if not message or not (10 <= len(message.strip()) <= 5000):
		frappe.throw(_("Please describe your project in 10–5000 characters."), frappe.ValidationError)
	if not cint(consent):
		frappe.throw(_("Contact consent is required."), frappe.ValidationError)


def _find_recent_duplicate(email_id: str):
	window = frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=-DEDUP_WINDOW_HOURS)
	return frappe.db.get_value(
		"Lead",
		filters={
			"email_id": email_id,
			"creation": (">=", window),
		},
		fieldname="name",
		order_by="creation desc",
	)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def submit_inquiry(**kwargs):
	full_name = (kwargs.get("full_name") or "").strip()
	email = (kwargs.get("email") or "").strip().lower()
	phone = (kwargs.get("phone") or "").strip()
	company = (kwargs.get("company") or "").strip()
	message = (kwargs.get("message") or "").strip()
	services = kwargs.get("services") or []
	source_url = (kwargs.get("source_url") or "").strip()
	website_url = (kwargs.get("website_url") or "").strip()

	# Honeypot: bots fill hidden fields; accept silently and discard.
	if website_url:
		return {"ok": True, "lead": None}

	_rate_limit()
	_validate_payload(full_name, email, services, message, kwargs.get("consent"))

	duplicate = _find_recent_duplicate(email)
	if duplicate:
		lead = frappe.get_doc("Lead", duplicate)
		lead.custom_vellox_inquiry = (
			f"{lead.custom_vellox_inquiry or ''}\n\n--- follow-up submission ---\n{message}"
		).strip()
		lead.save(ignore_permissions=True)
		return {"ok": True, "lead": lead.name}

	lead = frappe.new_doc("Lead")
	lead.lead_name = company or full_name
	lead.email_id = email
	if phone:
		lead.phone = phone
	if company:
		lead.company_name = company
	lead.custom_vellox_inquiry = message
	lead.custom_vellox_services = json.dumps(list(dict.fromkeys(services)))
	lead.custom_vellox_consent = 1
	if source_url:
		lead.custom_vellox_source_url = source_url[:140]
	lead.insert(ignore_permissions=True)

	return {"ok": True, "lead": lead.name}
