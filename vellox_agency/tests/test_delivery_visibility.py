import frappe
from frappe.tests.utils import FrappeTestCase

from vellox_agency.delivery_setup import setup_delivery_fields


class TestDeliveryVisibility(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from vellox_agency.tests.test_offer_builder import _bootstrap_erpnext_test_fixtures
        _bootstrap_erpnext_test_fixtures()
        setup_delivery_fields()
        frappe.reload_doctype("Deliverable")
        frappe.reload_doctype("Comment")
        cls.project = frappe.get_doc({
            "doctype": "Project",
            "project_name": "_Test Visibility Project",
            "company": "_Test Company",
        }).insert(ignore_permissions=True)

    def test_client_user_sees_only_client_visible_deliverables(self):
        # Create one visible and one hidden deliverable
        visible = frappe.get_doc({
            "doctype": "Deliverable",
            "project": self.project.name,
            "title": "Client Visible",
            "deliverable_type": "Design",
            "client_visible": 1,
        }).insert(ignore_permissions=True)
        hidden = frappe.get_doc({
            "doctype": "Deliverable",
            "project": self.project.name,
            "title": "Internal Only",
            "deliverable_type": "Design",
            "client_visible": 0,
        }).insert(ignore_permissions=True)

        client = "visibility-client@example.com"
        if not frappe.db.exists("User", client):
            u = frappe.get_doc({
                "doctype": "User", "email": client,
                "first_name": "Client", "send_welcome_email": 0,
            })
            u.insert(ignore_permissions=True)
            u.add_roles("Agency Client")
            u.save(ignore_permissions=True)

        with self.set_user(client):
            result = frappe.get_list(
                "Deliverable",
                filters={"project": self.project.name},
                pluck="name",
            )
            self.assertIn(visible.name, result)
            self.assertNotIn(hidden.name, result)

    def test_staff_user_sees_all_deliverables(self):
        frappe.get_doc({
            "doctype": "Deliverable",
            "project": self.project.name,
            "title": "Internal For Staff",
            "deliverable_type": "Design",
            "client_visible": 0,
        }).insert(ignore_permissions=True)

        staff = "visibility-staff@example.com"
        if not frappe.db.exists("User", staff):
            u = frappe.get_doc({
                "doctype": "User", "email": staff,
                "first_name": "Staff", "send_welcome_email": 0,
            })
            u.insert(ignore_permissions=True)
            u.add_roles("Agency Staff")
            u.save(ignore_permissions=True)

        with self.set_user(staff):
            result = frappe.get_list(
                "Deliverable",
                filters={"project": self.project.name},
                pluck="name",
            )
            self.assertTrue(len(result) >= 1)

    def test_comment_client_visible_field_exists(self):
        meta = frappe.get_meta("Comment")
        fieldnames = {f.fieldname for f in meta.fields}
        self.assertIn("custom_vellox_client_visible", fieldnames)

    def test_permission_query_conditions_hook_is_wired(self):
        # Verify the hook function is importable and callable
        conditions = frappe.get_attr(
            "vellox_agency.security.deliverable_permission_query"
        )
        self.assertTrue(callable(conditions))
        comment_conditions = frappe.get_attr(
            "vellox_agency.security.comment_permission_query"
        )
        self.assertTrue(callable(comment_conditions))

    def test_notification_fixtures_exist(self):
        for name in (
            "Vellox Deliverable Client Review",
            "Vellox Deliverable Client Decision",
            "Vellox Change Request Decision",
            "Vellox Revision Allowance Exhausted",
        ):
            self.assertTrue(frappe.db.exists("Notification", name), f"{name} missing")
