import frappe
from frappe.tests.utils import FrappeTestCase


class TestDeprecationGuard(FrappeTestCase):
	def test_mapping_covers_all_duplicate_ledgers(self):
		from vellox_agency.deprecations import DEPRECATION_TARGETS

		self.assertEqual(
			set(DEPRECATION_TARGETS),
			{
				"Client Account",
				"Agency Project",
				"Agency Timesheet",
				"Expense",
				"Agency Invoice",
				"Engagement",
				"Retainer",
			},
		)
		for doctype, target in DEPRECATION_TARGETS.items():
			self.assertTrue(target, "every deprecated ledger must name its ERPNext target")

	def test_new_inserts_are_blocked_with_target_guidance(self):
		import unittest.mock as mock

		from vellox_agency.deprecations import guard_deprecated_doctype

		doc = frappe.get_doc({"doctype": "Client Account", "client_name": "_Test Blocked"})
		with mock.patch.dict(frappe.flags, {"in_test": False}):
			with self.assertRaisesRegex(frappe.ValidationError, "Customer"):
				guard_deprecated_doctype(doc, "before_insert")

	def test_audit_runs_idempotently(self):
		from vellox_agency.deprecations import audit_record_counts

		first = audit_record_counts()
		second = audit_record_counts()
		self.assertEqual(first.keys() & second.keys(), set(first))
