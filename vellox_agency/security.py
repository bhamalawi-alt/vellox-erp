"""Least-privilege baseline for Vellox ERP.

Roles are defined once here and applied idempotently on install and after
every migration. Deprecated custom ledgers keep read access for management
roles only; every other right is stripped at the permission layer so API
access is denied server-side, not merely hidden in the UI.
"""

import frappe
from frappe import _
from frappe.utils import cint

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
	# Projects Manager: ERPNext puts Project > Users at permlevel 1, writable only
	# by that role, and project members are how team-member access is granted.
	"Project Manager": ("Vellox Project Manager", "Projects User", "Projects Manager", "Sales User"),
	"Team Member": ("Vellox Team Member", "Projects User"),
	"Finance": ("Vellox Finance", "Accounts User", "Sales User", "Projects User"),
	"Operations": ("Vellox Operations", "Sales User", "Projects User", "Projects Manager"),
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


EDIT, VIEW, LINK, NONE = "edit", "view", "link", "none"
_LEVEL_RANK = {NONE: 0, LINK: 1, VIEW: 2, EDIT: 3}
# Rights a view-only job keeps in the record checks; write, create, delete,
# submit, cancel, amend and share are refused. Export follows ERPNext's
# role-level export right, so view-only users can still export what they see.
VIEW_RIGHTS = frozenset({"read", "select", "report", "print", "email"})
# "link": the record can be referenced but not opened, listed or searched.
# Accounts and cost centers need this so quotes and projects save: ERPNext's
# Sales User gets select-only rights on them (_sales_user_select_only), which
# makes ERPNext's own account checks ask for "select" and closes every
# endpoint that returns balances to anyone who can read an Account.
LINK_RIGHTS = frozenset({"select"})
SELECT_ONLY_FOR_SALES_USER = ("Account", "Cost Center")

# Money and cost records: Finance and Agency Manager only (owner, 2026-10-31).
MONEY_DOCTYPES = ("Sales Order", "Delivery Note", "POS Invoice", "POS Invoice Merge Log", "Account", "Cost Center")
QUALITY_DOCTYPES = (
	"Quality Action",
	"Quality Feedback",
	"Quality Goal",
	"Quality Meeting",
	"Quality Procedure",
	"Quality Review",
)

# Record types whose access is capped per job. A job may never get more than
# its ERPNext roles grant; this only takes rights away. Anything a job's map
# leaves out is hidden from that job.
GOVERNED_DOCTYPES = (
	"Lead",
	"Opportunity",
	"Quotation",
	"Customer",
	"Contact",
	"Item",
	"Project",
	"Project Update",
	"Project Template",
	"Task",
	"Timesheet",
	"Activity Cost",
	"Sales Invoice",
	"Payment Entry",
	*MONEY_DOCTYPES,
	*QUALITY_DOCTYPES,
)
_QUALITY = dict.fromkeys(QUALITY_DOCTYPES, EDIT)
_TEAM_ACCESS = {"Project": VIEW, "Project Update": EDIT, "Task": EDIT, "Timesheet": EDIT}
JOB_ACCESS: dict[str, dict[str, str]] = {
	"Vellox Sales": {
		"Account": LINK,
		"Cost Center": LINK,
		"Lead": EDIT,
		"Opportunity": EDIT,
		"Quotation": EDIT,
		"Customer": EDIT,
		"Contact": EDIT,
		"Item": VIEW,
		**_QUALITY,
	},
	"Vellox Project Manager": {
		"Account": LINK,
		"Cost Center": LINK,
		"Project": EDIT,
		"Project Update": EDIT,
		"Project Template": VIEW,
		"Task": EDIT,
		"Timesheet": EDIT,
		"Activity Cost": EDIT,
		"Customer": VIEW,
		"Quotation": VIEW,
		"Contact": VIEW,
		"Item": VIEW,
		**_QUALITY,
	},
	"Vellox Team Member": dict(_TEAM_ACCESS),
	"Agency Staff": dict(_TEAM_ACCESS),
	"Vellox Finance": {
		"Sales Invoice": EDIT,
		"Payment Entry": EDIT,
		**dict.fromkeys(MONEY_DOCTYPES, EDIT),
		"Activity Cost": EDIT,
		"Customer": VIEW,
		"Quotation": VIEW,
		"Project": VIEW,
		"Project Update": VIEW,
		"Project Template": VIEW,
		"Timesheet": VIEW,
		"Contact": VIEW,
		"Item": VIEW,
		**_QUALITY,
	},
	"Vellox Operations": {
		"Account": LINK,
		"Cost Center": LINK,
		"Quotation": EDIT,
		"Project": EDIT,
		"Project Update": EDIT,
		"Project Template": VIEW,
		"Task": EDIT,
		"Activity Cost": EDIT,
		"Lead": VIEW,
		"Opportunity": VIEW,
		"Customer": VIEW,
		"Contact": VIEW,
		"Timesheet": VIEW,
		"Item": VIEW,
		**_QUALITY,
	},
	"Agency Manager": dict.fromkeys(GOVERNED_DOCTYPES, EDIT),
}
# Team members see only projects they are listed on (Project > Users), those
# projects' tasks, deliverables and updates, and only their own timesheets,
# unless another job of theirs sees more.
TEAM_ROLES = frozenset({"Vellox Team Member", "Agency Staff"})
TEAM_SCOPED_DOCTYPES = ("Project", "Project Update", "Task", "Timesheet", "Deliverable")


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


def _member_projects(user: str) -> set[str]:
	return set(
		frappe.get_all("Project User", filters={"parenttype": "Project", "user": user}, pluck="parent")
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
	if level == LINK and ptype and ptype not in LINK_RIGHTS:
		return False
	if doc.doctype in TEAM_SCOPED_DOCTYPES and _team_scoped(user) and not _team_can_access(doc, user):
		return False
	return None


def _team_can_access(doc, user: str) -> bool:
	members = _member_projects(user)
	if doc.doctype == "Project":
		return doc.name in members
	if doc.doctype == "Task" and not doc.get("project"):
		# A task outside any project: theirs if they created it or it is assigned to them.
		return doc.is_new() or doc.owner == user or user in frappe.parse_json(doc.get("_assign") or "[]")
	if doc.doctype != "Timesheet":
		return doc.get("project") in members
	if not (doc.is_new() or doc.owner == user):
		return False
	# Time may only be logged against the member's own projects (or none).
	for log in doc.get("time_logs") or []:
		projects = {log.project} if log.project else set()
		if log.task:
			projects.add(frappe.db.get_value("Task", log.task, "project"))
		if any(project and project not in members for project in projects):
			return False
	return True


def job_access_query(user=None, doctype=None) -> str:
	"""permission_query_conditions hook: the list-view side of job_access_permission."""
	user = user or frappe.session.user
	if access_level(doctype, user) in (NONE, LINK):
		return "1=0"
	if doctype not in TEAM_SCOPED_DOCTYPES or not _team_scoped(user):
		return ""
	if doctype == "Timesheet":
		return f"`tabTimesheet`.`owner` = {frappe.db.escape(user)}"
	if doctype == "Project":
		return f"`tabProject`.`name` in ({_member_projects_sql(user)})"
	condition = f"`tab{doctype}`.`project` in ({_member_projects_sql(user)})"
	if doctype == "Task":
		literal = user.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
		escaped, assigned = frappe.db.escape(user), frappe.db.escape(f'%"{literal}"%')
		condition = (
			f"({condition} or (ifnull(`tabTask`.`project`, '') = '' and "
			f"(`tabTask`.`owner` = {escaped} or `tabTask`.`_assign` like {assigned})))"
		)
	return condition


def job_access_file_query(user=None, doctype=None) -> str:
	"""permission_query_conditions for File: hide attachments of records the user cannot see.

	Frappe's own File list check is role-level only, so file names attached to
	hidden or out-of-scope records would otherwise show.
	"""
	user = user or frappe.session.user
	if not _job_roles(user):
		return ""
	attached = "ifnull(`tabFile`.`attached_to_doctype`, '')"
	conditions = []
	hidden = [doctype for doctype in GOVERNED_DOCTYPES if access_level(doctype, user) in (NONE, LINK)]
	if hidden:
		conditions.append(f"{attached} not in ({', '.join(frappe.db.escape(d) for d in hidden)})")
	if _team_scoped(user):
		members = _member_projects_sql(user)
		allowed = [
			f"(`tabFile`.`attached_to_doctype` = 'Project' and `tabFile`.`attached_to_name` in ({members}))",
			"(`tabFile`.`attached_to_doctype` = 'Timesheet' and `tabFile`.`attached_to_name` in "
			f"(select `name` from `tabTimesheet` where `owner` = {frappe.db.escape(user)}))",
		]
		for scoped in ("Task", "Deliverable", "Project Update"):
			allowed.append(
				f"(`tabFile`.`attached_to_doctype` = '{scoped}' and `tabFile`.`attached_to_name` in "
				f"(select `name` from `tab{scoped}` where `project` in ({members})))"
			)
		scoped_list = ", ".join(f"'{d}'" for d in TEAM_SCOPED_DOCTYPES)
		conditions.append(f"({attached} not in ({scoped_list}) or {' or '.join(allowed)})")
	return " and ".join(conditions)


def validate_todo_within_access(doc, method=None) -> None:
	"""ToDo validate hook: only someone who can open a record may assign it.

	Any user can create a ToDo, and its _assign update grants a team member
	access to a task without a project; Frappe's assign button checks that the
	assigner can read the record, a direct ToDo insert does not.
	"""
	doctype, name = doc.reference_type, doc.reference_name
	if not doctype or not name or (doctype not in GOVERNED_DOCTYPES and doctype not in TEAM_SCOPED_DOCTYPES):
		return
	if not _todo_grants_access(doc):
		return
	# Assignment rules and assign_to (which checks the assigner itself) insert
	# with ignore_permissions; a user's own ToDo insert never carries that flag.
	if doc.flags.ignore_permissions:
		return
	if frappe.session.user == "Administrator" or not frappe.db.exists(doctype, name):
		return
	if not frappe.has_permission(doctype, "read", doc=name):
		frappe.throw(
			_("You cannot assign {0} {1}: you do not have access to it.").format(_(doctype), frappe.bold(name)),
			frappe.PermissionError,
			title=_("Assignment not allowed"),
		)


def _todo_grants_access(doc) -> bool:
	"""True if this ToDo save could add someone to a record's _assign."""
	if doc.status != "Open":
		return False  # cancelled or closed ToDos are left out of _assign
	before = None if doc.is_new() else doc.get_doc_before_save()
	if before is None:
		return True
	moved = any(doc.get(f) != before.get(f) for f in ("allocated_to", "reference_type", "reference_name"))
	return moved or before.status != "Open"


def remember_project_members(doc, method=None) -> None:
	"""Project before_validate hook: note the members this save lists.

	ERPNext shares a project with newly added members inside its own validate,
	before the Project User rows are written, so the share check below needs
	the in-memory member list to recognise them as members.
	"""
	frappe.flags.setdefault("vellox_project_members", {})[doc.name] = {row.user for row in doc.users}


def forget_project_members(doc, method=None) -> None:
	"""Project on_update hook: the members noted by remember_project_members are stored now."""
	(frappe.flags.get("vellox_project_members") or {}).pop(doc.name, None)


def _being_added_as_member(user: str, project: str) -> bool:
	return user in (frappe.flags.get("vellox_project_members") or {}).get(project, set())


def validate_share_within_job(doc, method=None) -> None:
	"""DocShare validate hook: a share (or assignment) can never give more than the receiver's job.

	Frappe lets a share override has_permission; the owner decided (2026-10-31)
	that shares must stay within the person's job. Assigning a record to someone
	who cannot see it fails here with this message.
	"""
	doctype, name = doc.share_doctype, doc.share_name
	if doctype not in GOVERNED_DOCTYPES and doctype not in TEAM_SCOPED_DOCTYPES:
		return
	if not _share_grants_more(doc):
		return  # lowering or removing rights is always allowed
	if doc.everyone:
		frappe.throw(
			_("{0} records cannot be shared with everyone; access follows each person's job.").format(_(doctype)),
			frappe.PermissionError,
			title=_("Share not allowed"),
		)
	user = doc.user
	level = access_level(doctype, user)
	wants_change = doc.write or doc.submit or doc.share
	target = frappe.get_doc(doctype, name)
	out_of_scope = (
		doctype in TEAM_SCOPED_DOCTYPES
		and _team_scoped(user)
		and not _team_can_access(target, user)
		and not (doctype == "Project" and not wants_change and _being_added_as_member(user, name))
	)
	if level in (NONE, LINK) or (level == VIEW and wants_change) or out_of_scope:
		frappe.throw(
			_("Cannot share {0} {1} with {2}: their job does not allow {3} access to it. Change their role instead.").format(
				_(doctype), frappe.bold(name), frappe.bold(user), _("edit") if wants_change else _("view")
			),
			frappe.PermissionError,
			title=_("Share not allowed"),
		)


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
		setup_sales_notifications,
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
	setup_sales_notifications()
	_ensure_client_comment_permission()
	setup_roles_and_permissions()
	revoke_shares_beyond_jobs()
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
	_sales_user_select_only()
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

	Agency Client users see only client_visible deliverables. Team members
	are further limited to their projects by job_access_query ([P3-140]).
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


_SHARE_RIGHTS = ("read", "write", "submit", "share", "everyone")


def _share_grants_more(doc) -> bool:
	"""True if this DocShare save adds any right it did not have before."""
	before = None if doc.is_new() else doc.get_doc_before_save()
	if before and any(doc.get(f) != before.get(f) for f in ("user", "share_doctype", "share_name")):
		return True  # moved to another person or record: check it like a new share
	return any(cint(doc.get(right)) > cint(before.get(right) if before else 0) for right in _SHARE_RIGHTS)


def revoke_shares_beyond_jobs() -> int:
	"""Remove or reduce existing shares that give more than the receiver's job allows.

	Shares made before [P3-140], or before someone's job changed, bypassed
	validate_share_within_job. Runs after every migrate and hourly. Returns
	the number of shares changed.
	"""
	logger = frappe.logger("vellox_share_cleanup", allow_site=True)
	changed = 0
	for share in frappe.get_all(
		"DocShare",
		filters={"share_doctype": ["in", list(set(GOVERNED_DOCTYPES) | set(TEAM_SCOPED_DOCTYPES))]},
		fields=["name", "share_doctype", "share_name", "user", "everyone", "write", "submit", "share"],
	):
		if share.everyone:
			action = "remove"
		elif not share.user or not _job_roles(share.user):
			continue
		else:
			level = access_level(share.share_doctype, share.user)
			target = frappe.db.exists(share.share_doctype, share.share_name) and frappe.get_doc(
				share.share_doctype, share.share_name
			)
			out_of_scope = (
				target
				and share.share_doctype in TEAM_SCOPED_DOCTYPES
				and _team_scoped(share.user)
				and not _team_can_access(target, share.user)
			)
			if not target or level in (NONE, LINK) or out_of_scope:
				action = "remove"
			elif level == VIEW and (share.write or share.submit or share.share):
				action = "reduce"
			else:
				continue
		try:
			if action == "remove":
				_remove_share(share)
			else:
				frappe.db.set_value("DocShare", share.name, {"write": 0, "submit": 0, "share": 0})
		except Exception:
			# One bad row must not stop the run: this also runs inside bench migrate.
			frappe.log_error(title=f"Vellox share cleanup failed for DocShare {share.name}")
			continue
		logger.info("%s share %s (%s %s -> %s)", action, share.name, share.share_doctype, share.share_name, share.user or "everyone")
		changed += 1
	return changed


def _remove_share(share) -> None:
	if not frappe.db.exists(share.share_doctype, share.share_name):
		# DocShare.on_trash comments on the shared record, which is gone.
		frappe.db.delete("DocShare", share.name)
		return
	frappe.delete_doc("DocShare", share.name, ignore_permissions=True, flags={"ignore_share_permission": True})
	if not share.user:
		return
	# An assignment the person can no longer open would just sit in their list.
	for todo in frappe.get_all(
		"ToDo",
		filters={
			"allocated_to": share.user,
			"reference_type": share.share_doctype,
			"reference_name": share.share_name,
			"status": "Open",
		},
		pluck="name",
	):
		todo_doc = frappe.get_doc("ToDo", todo)
		todo_doc.status = "Cancelled"
		todo_doc.save(ignore_permissions=True)


def _sales_user_select_only() -> None:
	"""ERPNext's Sales User: select, not read, on accounts and cost centers ([P3-140]).

	Read access let Sales, PM and Operations fetch account balances through
	ERPNext endpoints that only check read (get_balance_on). With select only,
	ERPNext's own checks ask for select and quotes and projects still save.
	This sets up Custom DocPerm for these two doctypes, so later ERPNext changes
	to their standard permissions no longer apply automatically.
	"""
	from frappe.permissions import setup_custom_perms, update_permission_property

	for doctype in SELECT_ONLY_FOR_SALES_USER:
		setup_custom_perms(doctype)
		row = frappe.db.get_value(
			"Custom DocPerm",
			{"parent": doctype, "role": "Sales User", "permlevel": 0, "if_owner": 0},
			["read", "select"],
			as_dict=True,
		)
		if not row or (not row.read and row.select):
			continue
		update_permission_property(doctype, "Sales User", 0, "read", 0, validate=False)
		update_permission_property(doctype, "Sales User", 0, "select", 1)
		frappe.clear_cache(doctype=doctype)
