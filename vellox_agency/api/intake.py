"""Secured website inquiry intake — design section 2 of the approved
Lead-to-Project specification ([P2-16]/[P2-17]).

Guests can reach ONLY this endpoint. Submissions are validated, rate-limited
per visitor and per mailbox, merged into an existing Lead for the same email, and stored on
standard Lead records with consent metadata.
"""

import ipaddress
import json
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import cint, validate_email_address

from vellox_agency.setup.commercial import PRACTICES

MAX_PER_HOUR = 5
# Submissions per mailbox per day: each new Lead sends that mailbox an
# acknowledgement, so this caps the mail anyone can make Vellox send to one inbox.
MAX_PER_ADDRESS = 3
DEDUP_WINDOW_HOURS = 24
RATE_LIMIT_KEY = "vellox_intake"
GMAIL_DOMAINS = ("gmail.com", "googlemail.com")


def _client_ip() -> str:
	"""The visitor's address, as Frappe resolves it for its own rate limits.

	Frappe reads X-Forwarded-For first; bench's nginx config overwrites that
	header with the real connection address, so a visitor cannot pick their own
	bucket. Behind a CDN or second proxy, nginx needs real_ip settings (trusting
	only the CDN's ranges) for the same guarantee. ([P3-145]: this used to read
	frappe.local.client_ip, which Frappe never sets, so every visitor shared one limit.)
	"""
	return getattr(frappe.local, "request_ip", None) or "unknown"


def _visitor(ip: str) -> str:
	"""One bucket per IPv4 address, or per IPv6 /64: one connection gets a whole
	/64, so counting single IPv6 addresses would let anyone rotate past the limit."""
	try:
		address = ipaddress.ip_address(ip)
	except ValueError:
		return ip
	if address.version == 6:
		if address.ipv4_mapped:
			return str(address.ipv4_mapped)
		return str(ipaddress.ip_network(f"{address}/64", strict=False))
	return str(address)


def _mailbox(email: str) -> str:
	"""The inbox an address delivers to: no +tag, and Gmail ignores dots."""
	local, _, domain = email.strip().lower().rpartition("@")
	local = local.split("+", 1)[0]
	if domain in GMAIL_DOMAINS:
		local, domain = local.replace(".", ""), "gmail.com"
	return f"{local}@{domain}"


def _ip_key(ip: str | None = None) -> str:
	return frappe.cache().make_key(f"{RATE_LIMIT_KEY}:ip:{_visitor(ip or _client_ip())}")


def _mailbox_key(email: str) -> str:
	return frappe.cache().make_key(f"{RATE_LIMIT_KEY}:mailbox:{_mailbox(email)}")


def reset_rate_limit(ip: str | None = None) -> None:
	frappe.cache().delete(_ip_key(ip))


def reset_all_rate_limits() -> None:
	frappe.cache().delete_keys(RATE_LIMIT_KEY)


def _hit(key: str, limit: int, seconds: int, message: str) -> None:
	cache = frappe.cache()
	# Start the window before counting (as frappe.rate_limiter does), so a crash
	# between the two steps can never leave a counter without an expiry.
	cache.set(key, 0, ex=seconds, nx=True)
	if cint(cache.incr(key)) > limit:
		frappe.throw(message, frappe.exceptions.TooManyRequestsError)


def _rate_limit() -> None:
	_hit(_ip_key(), MAX_PER_HOUR, 3600, _("Too many inquiries from your network. Please try again later."))


def _limit_mailbox(email: str) -> None:
	_hit(
		_mailbox_key(email),
		MAX_PER_ADDRESS,
		24 * 3600,
		_("Too many inquiries for this email address today. Please try again tomorrow."),
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
	"""The Lead a new inquiry joins instead of creating another.

	When ERPNext allows only one Lead per email (the default), a later inquiry
	joins that Lead whatever its age; inserting would fail and lose it.
	"""
	filters = {"email_id": email_id}
	if frappe.db.get_single_value("CRM Settings", "allow_lead_duplication_based_on_emails"):
		filters["creation"] = (">=", frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=-DEDUP_WINDOW_HOURS))
	return frappe.db.get_value("Lead", filters=filters, fieldname="name", order_by="creation desc")


@contextmanager
def _as_intake_writer():
	"""Write the already-validated inquiry as Administrator.

	Assignment rules share a new lead with any assignee who cannot see it, and
	Frappe checks that share as the session user; for a Guest request it would
	fail and the visitor's inquiry would be lost. Only the Lead write runs here.

	frappe.set_user also replaces the session's sid and data and the request's
	form_dict, so all of them are restored; otherwise a logged-in visitor's
	real session would be overwritten when the request ends.
	"""
	local = frappe.local
	user, sid, data, form_dict = local.session.user, local.session.sid, local.session.data, local.form_dict
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		frappe.set_user(user)
		local.session.sid, local.session.data, local.form_dict = sid, data, form_dict


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
	_limit_mailbox(email)

	duplicate = _find_recent_duplicate(email)
	if duplicate:
		lead = frappe.get_doc("Lead", duplicate)
		lead.custom_vellox_inquiry = (
			f"{lead.custom_vellox_inquiry or ''}\n\n--- follow-up submission ---\n{message}"
		).strip()
		with _as_intake_writer():
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
	with _as_intake_writer():
		lead.insert(ignore_permissions=True)

	return {"ok": True, "lead": lead.name}
