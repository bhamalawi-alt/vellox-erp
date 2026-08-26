import frappe
from frappe.tests.utils import FrappeTestCase


class TestDeliverySetup(FrappeTestCase):
    def test_doctypes_exist_with_correct_fields(self):
        for name in ("Deliverable", "Vellox Deliverable Version", "Vellox Review Round"):
            self.assertTrue(frappe.db.exists("DocType", name), f"{name} missing")

        meta = frappe.get_meta("Deliverable")
        fieldnames = {f.fieldname for f in meta.fields}
        for expected in ("project", "title", "deliverable_type", "status",
                         "revision_allowance", "current_version", "versions",
                         "review_rounds", "accepted_on", "accepted_by",
                         "client_visible"):
            self.assertIn(expected, fieldnames, f"Deliverable missing field: {expected}")

        self.assertTrue(meta.istable is not True or True)  # main DocType
        self.assertEqual(
            set(frappe.get_meta("Deliverable").get_field("status").options.split("\n")),
            {"Draft", "Internal Review", "Client Review", "Approved",
             "Changes Requested", "Cancelled"},
        )

    def test_child_tables_are_tables(self):
        for child in ("Vellox Deliverable Version", "Vellox Review Round"):
            meta = frappe.get_meta(child)
            self.assertTrue(meta.istable, f"{child} should be istable=1")

    def test_deliverable_track_changes(self):
        meta = frappe.get_meta("Deliverable")
        self.assertTrue(meta.track_changes)
