"""Least-privilege baseline for Vellox ERP.

Roles are defined once here and applied idempotently on install and after
every migration. Deprecated custom ledgers keep read access for management
roles only; every other right is stripped at the permission layer so API
access is denied server-side, not merely hidden in the UI.
"""

import frappe

from vellox_agency.deprecations import DEPRECATION_TARGETS
from vellox_agency.delivery_setup import setup_delivery_fields

ROLE_MATRIX: dict[str, dict] = {
	"Vellox Sales": {"desk_access": 1},
	"Vellox Project Manager": {"desk_access": 1},
	"Vellox Team Member": {"desk_access": 1},
	"Vellox Finance": {"desk_access": 1},
	"Vellox Operations": {"desk_access": 1},
	"Agency Manager": {"desk_access": 1},
	"Agency Staff": {"desk_access": 1},
	"Agency Client": {"desk_access": 0},
}

MANAGEMENT_ROLES = ("System Manager", "Agency Manager")

# One Role Profile per job ([P3-140]). The ERPNext roles bring the base access
# (and the many linked records a quote or invoice needs); JOB_ACCESS below then
# limits each Vellox role to the owner-approved table.
JOB_PROFILES: dict[str, tuple[str, ...]] = {
	"Sales": ("Vellox Sales", "Sales User"),
	"Project Manager": ("Vellox Project Manager", "Projects User", "Sales User"),
	"Team Member": ("Vellox Team Member", "Projects User"),
	"Finance": ("Vellox Finance", "Accounts User", "Sales User", "Projects User"),
	"Operations": ("Vellox Operations", "Sales User", "Projects User"),
	"Agency Manager": (
		"Agency Manager",
		"Sales Manager",
		"Sales User",
		"Projects Manager",
		"Projects User",
		"Accounts Manager",
		"Accounts User",
	),
	"Agency Staff": ("Agency Staff", "Projects User"),
}


EDIT, VIEW, NONE = "edit", "view", "none"
_LEVEL_RANK = {NONE: 0, VIEW: 1, EDIT: 2}
# Rights a view-only job keeps; everything else (write, create, delete,
# submit, cancel, amend, share, export, import) is refused.
VIEW_RIGHTS = frozenset({"read", "select", "report", "print", "email"})

# Record types whose access is capped per job. A job may never get more than
# its ERPNext roles grant; this only takes rights away.
GOVERNED_DOCTYPES = (
	"Lead",
	"Opportunity",
	"Quotation",
	"Customer",
	"Contact",
	"Item",
	"Project",
	"Task",
	"Timesheet",
	"Sales Invoice",
	"Payment Entry",
)
_TEAM_ACCESS = {"Project": VIEW, "Task": EDIT, "Timesheet": EDIT}
JOB_ACCESS: dict[str, dict[str, str]] = {
	"Vellox Sales": {
		"Lead": EDIT,
		"Opportunity": EDIT,
		"Quotation": EDIT,
		"Customer": EDIT,
		"Contact": EDIT,
		"Item": VIEW,
	},
	"Vellox Project Manager": {
		"Project": EDIT,
		"Task": EDIT,
		"Timesheet": EDIT,
		"Customer": VIEW,
		"Quotation": VIEW,
		"Contact": VIEW,
		"Item": VIEW,
	},
	"Vellox Team Member": dict(_TEAM_ACCESS),
	"Agency Staff": dict(_TEAM_ACCESS),
	"Vellox Finance": {
		"Sales Invoice": EDIT,
		"Payment Entry": EDIT,
		"Customer": VIEW,
		"Quotation": VIEW,
		"Project": VIEW,
		"Timesheet": VIEW,
		"Contact": VIEW,
		"Item": VIEW,
	},
	"Vellox Operations": {
		"Quotation": EDIT,
		"Project": EDIT,
		"Task": EDIT,
		"Lead": VIEW,
		"Opportunity": VIEW,
		"Customer": VIEW,
		"Contact": VIEW,
		"Timesheet": VIEW,
		"Item": VIEW,
	},
	"Agency Manager": dict.fromkeys(GOVERNED_DOCTYPES, EDIT),
}
# Team members see only projects they are listed on (Project > Users) and
# only their own timesheets, unless another job of theirs sees more.
TEAM_ROLES = frozenset({"Vellox Team Member", "Agency Staff"})
TEAM_SCOPED_DOCTYPES = ("Project", "Task", "Timesheet", "Deliverable")


def _job_roles(user: str) -> set[str]:
	"""The user's Vellox job roles, or an empty set when no cap applies."""
	if user == "Administrator":
		return set()
	roles = set(frappe.get_roles(user))
	if "System Manager" in roles:
		return set()
	return roles & set(JOB_ACCESS)


def access_level(doctype: str, user: str | None = None) -> str | None:
	"""Highest level any of the user's jobs allows on doctype; None when uncapped."""
	jobs = _job_roles(user or frappe.session.user)
	if not jobs or doctype not in GOVERNED_DOCTYPES:
		return None
	return max((JOB_ACCESS[job].get(doctype, NONE) for job in jobs), key=_LEVEL_RANK.get)


def _team_scoped(user: str) -> bool:
	jobs = _job_roles(user)
	return bool(jobs) and jobs <= TEAM_ROLES


def _member_projects_sql(user: str) -> str:
	return (
		"select `parent` from `tabProject User` "
		f"where `parenttype` = 'Project' and `user` = {frappe.db.escape(user)}"
	)


def _is_project_member(user: str, project: str | None) -> bool:
	return bool(project) and frappe.db.exists(
		"Project User", {"parenttype": "Project", "parent": project, "user": user}
	)


def job_access_permission(doc, ptype=None, user=None, **kwargs) -> bool | None:
	"""has_permission hook: refuse what the user's jobs do not allow; otherwise stay silent.

	Returns None (not True) when allowing, so other apps' hooks still decide.
	"""
	user = user or frappe.session.user
	level = access_level(doc.doctype, user)
	if level == NONE:
		return False
	if level == VIEW and ptype and ptype not in VIEW_RIGHTS:
		return False
	if doc.doctype in TEAM_SCOPED_DOCTYPES and _team_scoped(user) and not _team_can_access(doc, user):
		return False
	return None


def _team_can_access(doc, user: str) -> bool:
	if doc.doctype == "Timesheet":
		return doc.is_new() or doc.owner == user
	if doc.doctype == "Project":
		return _is_project_member(user, doc.name)
	return _is_project_member(user, doc.get("project"))


def job_access_query(user=None, doctype=None) -> str:
	"""permission_query_conditions hook: the list-view side of job_access_permission."""
	user = user or frappe.session.user
	if access_level(doctype, user) == NONE:
		return "1=0"
	if doctype not in TEAM_SCOPED_DOCTYPES or not _team_scoped(user):
		return ""
	if doctype == "Timesheet":
		return f"`tabTimesheet`.`owner` = {frappe.db.escape(user)}"
	if doctype == "Project":
		return f"`tabProject`.`name` in ({_member_projects_sql(user)})"
	return f"`tab{doctype}`.`project` in ({_member_projects_sql(user)})"


def _profile_name(job: str) -> str:
	return job if job.startswith("Agency") else f"Vellox {job}"


def setup_job_profiles() -> None:
	"""Create or update one Role Profile per job; assigning it keeps a user's roles in sync."""
	for job, roles in JOB_PROFILES.items():
		name = _profile_name(job)
		if frappe.db.exists("Role Profile", name):
			profile = frappe.get_doc("Role Profile", name)
		else:
			profile = frappe.new_doc("Role Profile")
			profile.role_profile = name
		if sorted(r.role for r in profile.roles) == sorted(roles):
			continue
		profile.set("roles", [{"role": role} for role in roles])
		profile.save(ignore_permissions=True)


def apply_baseline() -> None:
	"""after_migrate hook: reapply offer metadata + least-privilege baseline."""
	from vellox_agency.crm_setup import (
		setup_change_request_doctype,
		setup_commercial_approval_fields,
		setup_crm_intake_fields,
		setup_lead_assignment_and_sla,
		setup_opportunity_pipeline,
		setup_project_health_field,
		setup_quotation_estimate_fields,
	)
	from vellox_agency.setup.commercial import setup_commercial_foundation
	from vellox_agency.setup.practice_templates import setup_practice_templates
	from vellox_agency.setup.offer_builder import setup_offer_builder

	setup_offer_builder()
	setup_commercial_foundation()
	setup_crm_intake_fields()
	setup_lead_assignment_and_sla()
	setup_opportunity_pipeline()
	setup_commercial_approval_fields()
	setup_project_health_field()
	setup_change_request_doctype()
	setup_delivery_fields()
	setup_practice_templates()
	setup_quotation_estimate_fields()
	_ensure_client_comment_permission()
	setup_roles_and_permissions()
	_report_lead_routing()


def _report_lead_routing() -> None:
	"""Re-sync lead routing after permissions are applied, and say so if it is off."""
	from vellox_agency.crm_setup import ASSIGNMENT_RULE, LEAD_ROSTER_ROLES, sync_lead_assignment_users

	sync_lead_assignment_users()
	if frappe.db.get_value("Assignment Rule", ASSIGNMENT_RULE, "disabled"):
		print(
			f"Vellox: lead routing is OFF. No active user with {' or '.join(LEAD_ROSTER_ROLES)} "
			"can see every Lead, so new website inquiries are not assigned to anyone. "
			"Set Role Profile 'Vellox Sales' on each salesperson's user."
		)


def setup_roles_and_permissions() -> None:
	for role_name, spec in ROLE_MATRIX.items():
		if frappe.db.exists("Role", role_name):
			role = frappe.get_doc("Role", role_name)
		else:
			role = frappe.new_doc("Role")
			role.role_name = role_name
		role.desk_access = spec["desk_access"]
		role.disabled = 0
		role.save(ignore_permissions=True)

	_strip_deprecated_doctype_permissions()
	setup_job_profiles()
	frappe.db.commit()


def _strip_deprecated_doctype_permissions() -> None:
	"""Reduce deprecated ledgers to read-only for management roles."""
	# DocType saves require developer mode; the framework's sanctioned
	# escape hatch for programmatic metadata maintenance is patch context.
	frappe.flags.in_patch = True
	try:
		for doctype in DEPRECATION_TARGETS:
			meta = frappe.get_doc("DocType", doctype)
			new_permissions = []
			for perm in meta.permissions or []:
				if perm.role not in MANAGEMENT_ROLES:
					continue
				for right in (
					"create",
					"write",
					"delete",
					"submit",
					"cancel",
					"amend",
					"export",
					"share",
					"print",
					"email",
				):
					setattr(perm, right, 0)
				perm.read = 1
				perm.permlevel = perm.permlevel or 0
				new_permissions.append(perm)
			meta.permissions = new_permissions
			meta.flags.ignore_permissions = True
			meta.save()
	finally:
		frappe.flags.in_patch = False


def _user_has_management_role(user: str | None) -> bool:
	user = user or frappe.session.user
	return bool(set(frappe.get_roles(user)) & set(MANAGEMENT_ROLES))


def has_deprecated_doctype_access(
	user=None, ptype="read", doc=None, doctype=None, **kwargs
) -> bool:
	"""has_permission hook: deny everything but read outside management."""
	doctype = doctype or getattr(doc, "doctype", None)
	if doctype not in DEPRECATION_TARGETS:
		return True
	if ptype != "read":
		return False
	return _user_has_management_role(user)


def deliverable_permission_query(user):
	"""permission_query_conditions hook for Deliverable.

	Agency Client users see only client_visible deliverables.
	All other roles see all deliverables (project-level filtering
	is deferred to the portal phase when User Permissions are wired).
	"""
	if not user:
		user = frappe.session.user
	roles = set(frappe.get_roles(user))
	if "Agency Client" in roles:
		return "tabDeliverable.client_visible = 1"
	return ""


def comment_permission_query(user):
	"""permission_query_conditions hook for Comment on Deliverable contexts.

	Agency Client users see only client-visible comments.
	"""
	if not user:
		user = frappe.session.user
	roles = set(frappe.get_roles(user))
	if "Agency Client" in roles:
		return "tabComment.custom_vellox_client_visible = 1"
	return ""


def _ensure_client_comment_permission() -> None:
	"""Grant Agency Client read-only access to Comment (core DocType)."""
	frappe.flags.in_patch = True
	try:
		meta = frappe.get_doc("DocType", "Comment")
		existing_roles = {p.role for p in meta.permissions or []}
		if "Agency Client" not in existing_roles:
			meta.append("permissions", {
				"role": "Agency Client",
				"read": 1,
			})
			meta.flags.ignore_permissions = True
			meta.save()
	finally:
		frappe.flags.in_patch = False
