"""Least-privilege baseline for Vellox ERP.

Roles are defined once here and applied idempotently on install and after
every migration. Deprecated custom ledgers keep read access for management
roles only; every other right is stripped at the permission layer so API
access is denied server-side, not merely hidden in the UI.
"""

import frappe

from vellox_agency.deprecations import DEPRECATION_TARGETS

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


def apply_baseline() -> None:
	"""after_migrate hook: reapply offer metadata + least-privilege baseline."""
	from vellox_agency.setup.offer_builder import setup_offer_builder

	setup_offer_builder()
	setup_roles_and_permissions()


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
	frappe.db.commit()


def _strip_deprecated_doctype_permissions() -> None:
	"""Reduce deprecated ledgers to read-only for management roles."""
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
