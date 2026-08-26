import frappe
from frappe.tests.utils import FrappeTestCase

from vellox_agency.delivery_setup import setup_delivery_fields
from vellox_agency.deliverable import transition


def _project_name():
    return frappe.db.get_value(
        "Project", {"project_name": "_Test Lifecycle Project"}, "name"
    )


def _deliverable(**kw):
    defaults = {
        "doctype": "Deliverable",
        "project": _project_name(),
        "title": "Brand Guidelines v2",
        "deliverable_type": "Design",
    }
    defaults.update(kw)
    return frappe.get_doc(defaults)


class TestDeliverableLifecycle(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from vellox_agency.tests.test_offer_builder import _bootstrap_erpnext_test_fixtures
        _bootstrap_erpnext_test_fixtures()
        setup_delivery_fields()
        frappe.reload_doctype("Deliverable")
        existing = frappe.db.get_value("Project", {"project_name": "_Test Lifecycle Project"}, "name")
        if existing:
            cls.project = frappe.get_doc("Project", existing)
        else:
            cls.project = frappe.get_doc({
                "doctype": "Project",
                "project_name": "_Test Lifecycle Project",
                "company": "_Test Company",
            }).insert(ignore_permissions=True)
            frappe.db.commit()

    def test_happy_path_draft_to_approved(self):
        doc = _deliverable().insert(ignore_permissions=True)
        self.assertEqual(doc.status, "Draft")
        transition(doc, "submit_for_review")
        self.assertEqual(doc.status, "Internal Review")
        transition(doc, "internal_approve")
        self.assertEqual(doc.status, "Client Review")
        doc.append("review_rounds", {
            "reviewer": "Administrator",
            "audience": "Client",
            "outcome": "Approved",
            "comments": "Looks great",
            "reviewed_on": frappe.utils.now_datetime(),
        })
        doc.save()
        transition(doc, "client_approve")
        self.assertEqual(doc.status, "Approved")

    def test_illegal_transition_raises(self):
        doc = _deliverable().insert(ignore_permissions=True)
        with self.assertRaisesRegex(frappe.ValidationError, "Illegal transition"):
            transition(doc, "client_approve")  # Draft -> Client Review is illegal

    def test_changes_requested_back_to_internal(self):
        doc = _deliverable().insert(ignore_permissions=True)
        transition(doc, "submit_for_review")
        transition(doc, "internal_approve")
        transition(doc, "request_changes")
        self.assertEqual(doc.status, "Changes Requested")
        transition(doc, "submit_for_review")
        self.assertEqual(doc.status, "Internal Review")

    def test_cancel_from_draft(self):
        doc = _deliverable().insert(ignore_permissions=True)
        transition(doc, "cancel")
        self.assertEqual(doc.status, "Cancelled")

    def test_cancel_not_allowed_after_internal_review(self):
        doc = _deliverable().insert(ignore_permissions=True)
        transition(doc, "submit_for_review")
        with self.assertRaisesRegex(frappe.ValidationError, "Illegal transition"):
            transition(doc, "cancel")

    def test_final_approve_requires_client_round(self):
        doc = _deliverable().insert(ignore_permissions=True)
        transition(doc, "submit_for_review")
        transition(doc, "internal_approve")
        # no client review round yet — should fail
        with self.assertRaisesRegex(frappe.ValidationError, "client.*review"):
            transition(doc, "client_approve")

    def test_current_version_increments(self):
        doc = _deliverable().insert(ignore_permissions=True)
        self.assertEqual(doc.current_version, 0)
        doc.append("versions", {
            "version_number": 1,
            "file_url": "https://example.com/v1.pdf",
            "created_by": "Administrator",
            "created_on": frappe.utils.now_datetime(),
        })
        doc.save()
        transition(doc, "submit_for_review")
        self.assertEqual(doc.current_version, 1)
