# Copyright (c) 2026, Vellox Team and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from vellox_agency.setup.offer_builder import setup_offer_builder

AGENCY_ROLES = [
	{
		"role_name": "Agency Manager",
		"desk_access": 1,
		"home_page": "/app/project",
		"disabled": 0,
	},
	{
		"role_name": "Agency Staff",
		"desk_access": 1,
		"home_page": "/app/project",
		"disabled": 0,
	},
	{
		"role_name": "Agency Client",
		"desk_access": 0,
		"disabled": 0,
	},
]


def after_install():
	for role in AGENCY_ROLES:
		create_role(role)
	setup_offer_builder()


def create_role(role_data):
	role_name = role_data.get("role_name")
	if not frappe.db.exists("Role", role_name):
		role = frappe.new_doc("Role")
		role.role_name = role_name
		role.desk_access = role_data.get("desk_access")
		role.home_page = role_data.get("home_page")
		role.disabled = role_data.get("disabled")
		role.insert()
		frappe.msgprint(_("Role {0} created").format(role_name), alert=True)
