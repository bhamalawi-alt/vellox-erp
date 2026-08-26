import frappe
from frappe.tests.utils import FrappeTestCase

from vellox_agency.delivery_setup import setup_delivery_fields
from vellox_agency.deliverable import transition


def _deliverable_with_version(**kw):
    """Insert a Draft deliverable with one version row attached."""
    project = frappe.db.get_value("Project", {"project_name": "_Test Version Project"}, "name")
    doc = frappe.get_doc({
        "doctype": "Deliverable",
        "project": project,
        "title": "Logo Concept",
        "deliverable_type": "Design",
        "revision_allowance": 2,
        "versions": [{
            "version_number": 1,
            "file_url": "https://example.com/logo-v1.pdf",
            "notes": "Initial draft",
            "created_by": "Administrator",
            "created_on": frappe.utils.now_datetime(),
        }],
    })
    doc.insert(ignore_permissions=True)
    return doc


class TestDeliverableVersions(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from vellox_agency.tests.test_offer_builder import _bootstrap_erpnext_test_fixtures
        _bootstrap_erpnext_test_fixtures()
        setup_delivery_fields()
        frappe.reload_doctype("Deliverable")
        existing = frappe.db.get_value("Project", {"project_name": "_Test Version Project"}, "name")
        if existing:
            cls.project = frappe.get_doc("Project", existing)
        else:
            cls.project = frappe.get_doc({
                "doctype": "Project",
                "project_name": "_Test Version Project",
                "company": "_Test Company",
            }).insert(ignore_permissions=True)
            frappe.db.commit()

    def test_version_immutability(self):
        doc = _deliverable_with_version()
        v = doc.versions[0]
        # Attempting to modify an existing version row should raise
        v.notes = "Modified after insert"
        with self.assertRaises(frappe.ValidationError):
            doc.save()

    def test_adding_new_version_creates_row(self):
        doc = _deliverable_with_version()
        self.assertEqual(len(doc.versions), 1)
        doc.append("versions", {
            "version_number": 2,
            "file_url": "https://example.com/logo-v2.pdf",
            "notes": "Revision 2",
            "created_by": "Administrator",
            "created_on": frappe.utils.now_datetime(),
        })
        doc.save()
        doc.reload()
        self.assertEqual(len(doc.versions), 2)

    def test_current_version_tracks_latest(self):
        doc = _deliverable_with_version()
        self.assertEqual(doc.current_version, 0)
        doc.append("versions", {
            "version_number": 2,
            "file_url": "https://example.com/logo-v2.pdf",
            "notes": "",
            "created_by": "Administrator",
            "created_on": frappe.utils.now_datetime(),
        })
        doc.current_version = 2
        doc.save()
        self.assertEqual(doc.current_version, 2)

    def test_revision_allowance_exhausted_blocks_submit(self):
        """When review_rounds consumed > revision_allowance, submit_for_review
        should force status to Changes Requested and require a CR."""
        project = frappe.db.get_value("Project", {"project_name": "_Test Version Project"}, "name")
        doc = frappe.get_doc({
            "doctype": "Deliverable",
            "project": project,
            "title": "Exhaustion Test",
            "deliverable_type": "Document",
            "revision_allowance": 1,
            "versions": [{
                "version_number": 1,
                "file_url": "https://example.com/doc-v1.pdf",
                "created_by": "Administrator",
                "created_on": frappe.utils.now_datetime(),
            }],
            "review_rounds": [{
                "reviewer": "Administrator",
                "audience": "Internal",
                "outcome": "Changes Requested",
                "comments": "Needs rework",
                "reviewed_on": frappe.utils.now_datetime(),
            }],
        }).insert(ignore_permissions=True)
        # 1 round consumed, allowance=1 → no exhaustion yet
        transition(doc, "submit_for_review")
        self.assertEqual(doc.status, "Internal Review")

        # Now add a second round (exceeds allowance=1)
        doc.append("review_rounds", {
            "reviewer": "Administrator",
            "audience": "Client",
            "outcome": "Changes Requested",
            "comments": "Client rejected",
            "reviewed_on": frappe.utils.now_datetime(),
        })
        doc.status = "Changes Requested"
        doc.save()
        # 2 rounds > allowance=1 → Changes Requested required
        with self.assertRaisesRegex(frappe.ValidationError, "Change Request"):
            transition(doc, "submit_for_review")

    def test_version_number_required(self):
        project = frappe.db.get_value("Project", {"project_name": "_Test Version Project"}, "name")
        doc = frappe.get_doc({
            "doctype": "Deliverable",
            "project": project,
            "title": "No Number",
            "deliverable_type": "Design",
            "versions": [{
                "file_url": "https://example.com/x.pdf",
                "created_by": "Administrator",
                "created_on": frappe.utils.now_datetime(),
            }],
        })
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)
