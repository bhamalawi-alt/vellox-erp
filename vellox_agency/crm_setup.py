"""Lead custom fields for the website intake flow (design section 2/3)."""

import frappe

LEAD_CUSTOM_FIELDS = {
	"Lead": [
		{
			"fieldname": "custom_vellox_services",
			"label": "Requested Services",
			"fieldtype": "Small Text",
			"insert_after": "request_type",
		},
		{
			"fieldname": "custom_vellox_inquiry",
			"label": "Inquiry Message",
			"fieldtype": "Long Text",
			"insert_after": "custom_vellox_services",
		},
		{
			"fieldname": "custom_vellox_first_response_due",
			"label": "First Response Due",
			"fieldtype": "Datetime",
			"insert_after": "custom_vellox_consent",
		},
		{
			"fieldname": "custom_vellox_qualified",
			"label": "Qualified",
			"fieldtype": "Check",
			"insert_after": "custom_vellox_first_response_due",
		},
		{
			"fieldname": "custom_vellox_consent",
			"label": "Contact Consent",
			"fieldtype": "Check",
			"insert_after": "custom_vellox_services",
		},
		{
			"fieldname": "custom_vellox_source_url",
			"label": "Source URL",
			"fieldtype": "Data",
			"insert_after": "custom_vellox_consent",
		},
	]
}


def setup_crm_intake_fields() -> None:
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(LEAD_CUSTOM_FIELDS, update=True)


STAGE_PROBABILITY = {
	"Prospecting": 10,
	"Qualified": 30,
	"Proposal Sent": 60,
	"Negotiation": 80,
}

LOST_REASONS = ["Price", "Delay in implementation", "Chose a competitor", "Project postponed"]

ASSIGNMENT_RULE = "Vellox Intake Assignment"
FIRST_RESPONSE_HOURS = 4
# New leads go round-robin to active users with the first role that has anyone.
LEAD_ROSTER_ROLES = ("Vellox Sales", "Agency Manager")
LEAD_RULE_DESCRIPTION = (
	"Managed by vellox_agency: new leads go round-robin to active users with the "
	"Vellox Sales role (or Agency Manager if nobody has it) who can see every Lead. "
	"Edits to Users or Disabled here are overwritten; change routing through those roles."
)


def setup_lead_assignment_and_sla() -> None:
	_ensure_sales_stage_prospecting()
	if not frappe.db.exists("Assignment Rule", ASSIGNMENT_RULE):
		frappe.get_doc(
			{
				"doctype": "Assignment Rule",
				"name": ASSIGNMENT_RULE,
				"title": ASSIGNMENT_RULE,
				"document_type": "Lead",
				"description": LEAD_RULE_DESCRIPTION,
				"rule": "Round Robin",
				"assign_condition": 'status == "Lead"',
				"priority": 1,
				"assignment_days": [
					{"day": day}
					for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
				],
			}
		).insert(ignore_permissions=True)
	sync_lead_assignment_users()


def lead_assignment_roster() -> list[str]:
	"""Active desk users who can see every Lead, from the first LEAD_ROSTER_ROLES role that has any.

	Users who cannot read Lead, or whose User Permissions restrict which Leads
	they see, are left out: Frappe shares a lead with an assignee who cannot
	see it, so new leads should only go to people who need no share.
	"""
	for role in LEAD_ROSTER_ROLES:
		holders = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent")
		holders = [user for user in holders if user not in ("Administrator", "Guest")]
		if not holders:
			continue
		users = frappe.get_all(
			"User",
			filters={"name": ["in", holders], "enabled": 1, "user_type": "System User"},
			pluck="name",
			order_by="name asc",
		)
		users = [
			user
			for user in users
			if frappe.has_permission("Lead", "read", user=user) and not _restricted_on_lead(user)
		]
		if users:
			return users
	return []


def _restricted_on_lead(user: str) -> bool:
	"""True if the user's User Permissions limit which Leads they can see."""
	from frappe.permissions import get_user_permissions

	restricting = set(get_user_permissions(user))
	if not restricting:
		return False
	lead_links = {"Lead"} | {df.options for df in frappe.get_meta("Lead").get_link_fields()}
	return bool(restricting & lead_links)


def sync_lead_assignment_users(doc=None, method=None) -> None:
	"""Keep the intake rule's users equal to the roster; disable it when nobody qualifies.

	Runs on migrate and as a hook on User, User Permission, Custom DocPerm and
	Role changes, so granting or removing access updates lead routing right
	away. An enabled rule with no users would crash Frappe's round-robin.
	"""
	if not frappe.db.exists("Assignment Rule", ASSIGNMENT_RULE):
		return
	roster = lead_assignment_roster()
	rule = frappe.get_doc("Assignment Rule", ASSIGNMENT_RULE)
	disabled = 0 if roster else 1
	# last_user is where round-robin resumes; a removed or deleted user there
	# would fail the rule's link validation on save.
	last_user = rule.last_user if rule.last_user in roster else None
	if (
		[u.user for u in rule.users] == roster
		and rule.disabled == disabled
		and rule.last_user == last_user
		and rule.description == LEAD_RULE_DESCRIPTION
	):
		return
	rule.set("users", [{"user": user} for user in roster])
	rule.disabled = disabled
	rule.last_user = last_user
	rule.description = LEAD_RULE_DESCRIPTION
	rule.save(ignore_permissions=True)
	if not roster:
		frappe.logger("vellox_lead_routing", allow_site=True).warning(
			"%s disabled: no active user with any of %s can see every Lead",
			ASSIGNMENT_RULE,
			", ".join(LEAD_ROSTER_ROLES),
		)


def _ensure_sales_stage_prospecting() -> None:
	if not frappe.db.exists("Sales Stage", "Prospecting"):
		frappe.get_doc({"doctype": "Sales Stage", "stage_name": "Prospecting"}).insert(
			ignore_permissions=True
		)


def setup_opportunity_pipeline() -> None:
	"""Stages with approved probabilities + standard lost reasons."""
	from vellox_agency.setup.commercial import setup_commercial_foundation

	setup_commercial_foundation()  # guarantees UOM/company-independent masters
	_ensure_sales_stage_prospecting()
	if not frappe.db.exists("Opportunity Type", "Sales"):
		frappe.get_doc({"doctype": "Opportunity Type", "__newname": "Sales", "opportunity_type": "Sales"}).insert(
			ignore_permissions=True
		)

	for stage in STAGE_PROBABILITY:
		if not frappe.db.exists("Sales Stage", stage):
			frappe.get_doc({"doctype": "Sales Stage", "stage_name": stage}).insert(
				ignore_permissions=True
			)

	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
	create_custom_fields(
		{
			"Opportunity": [
				{
					"fieldname": "custom_vellox_probability",
					"label": "Vellox Probability (%)",
					"fieldtype": "Percent",
					"insert_after": "sales_stage",
				}
			],
			"Sales Stage": [
				{
					"fieldname": "custom_vellox_probability",
					"label": "Probability (%)",
					"fieldtype": "Percent",
					"insert_after": "stage_name",
				}
			],
		},
		update=True,
	)
	for stage, prob in STAGE_PROBABILITY.items():
		frappe.db.set_value("Sales Stage", stage, "custom_vellox_probability", prob)

	for reason in LOST_REASONS:
		if not frappe.db.exists("Opportunity Lost Reason", reason):
			frappe.get_doc(
				{"doctype": "Opportunity Lost Reason", "lost_reason": reason}
			).insert(ignore_permissions=True)
	frappe.db.commit()


QUOTATION_ESTIMATE_FIELDS = [
	{
		"fieldname": "custom_vellox_estimate_hours",
		"label": "Estimate Hours (role/hours/rate JSON)",
		"fieldtype": "Small Text",
		"insert_after": "custom_vellox_technical_proposal",
	},
	{
		"fieldname": "custom_vellox_vendor_cost",
		"label": "Vendor Cost (company currency)",
		"fieldtype": "Currency",
		"insert_after": "custom_vellox_estimate_hours",
	},
	{
		"fieldname": "custom_vellox_estimated_margin",
		"label": "Estimated Margin %",
		"fieldtype": "Percent",
		"insert_after": "custom_vellox_vendor_cost",
		"read_only": 1,
	},
]


def setup_commercial_approval_fields() -> None:
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(
		{
			"Quotation": [
				{
					"fieldname": "custom_vellox_approval_status",
					"label": "Approval Status",
					"fieldtype": "Select",
					"options": "Pending\nApproved\nNot Approved",
					"default": "Pending",
					"insert_after": "custom_vellox_estimated_margin",
				},
				{
					"fieldname": "custom_vellox_approved_by",
					"label": "Approved By",
					"fieldtype": "Data",
					"read_only": 1,
					"insert_after": "custom_vellox_approval_status",
				},
			]
		},
		update=True,
	)


def setup_quotation_estimate_fields() -> None:
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields({"Quotation": QUOTATION_ESTIMATE_FIELDS}, update=True)


def _ensure_uom() -> None:
	pass


def stamp_first_response_due(doc, method=None) -> None:
	from frappe.utils import add_to_date, now_datetime

	if doc.doctype == "Lead" and not doc.custom_vellox_first_response_due:
		doc.custom_vellox_first_response_due = add_to_date(now_datetime(), hours=FIRST_RESPONSE_HOURS)


PROJECT_HEALTH_FIELD = {
	"fieldname": "custom_vellox_health",
	"label": "Project Health",
	"fieldtype": "Select",
	"options": "On Track\nAt Risk\nOff Track",
	"default": "On Track",
	"insert_after": "expected_end_date",
}


def setup_project_health_field() -> None:
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields({"Project": [PROJECT_HEALTH_FIELD]}, update=True)


HEALTH_MANAGER_ROLES = ("System Manager", "Agency Manager", "Vellox Project Manager")
CR_LEGAL_TRANSITIONS = {
	"Draft": {"Under Review"},
	"Under Review": {"Approved", "Rejected"},
	"Approved": {"Implemented", "Closed"},
	"Rejected": {"Closed", "Under Review"},
	"Implemented": {"Closed"},
}
PM_APPROVE_ROLES = ("System Manager", "Agency Manager", "Vellox Project Manager")


def setup_change_request_doctype() -> None:
	if not frappe.db.exists("DocType", "Vellox Change Request"):
		frappe.reload_doc("vellox_agency_projects", "doctype", "vellox_change_request")
	frappe.reload_doc("vellox_agency_projects", "doctype", "vellox_change_request")
