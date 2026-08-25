import frappe
from frappe.tests.utils import FrappeTestCase


class TestRuntimeCompatibility(FrappeTestCase):
	def test_current_bench_passes_validation(self):
		from vellox_agency.compatibility import validate_runtime_compatibility

		validate_runtime_compatibility()

	def test_unsupported_major_version_is_rejected_with_action(self):
		import unittest.mock as mock

		from vellox_agency import compatibility

		fake = {"frappe": "16.0.1", "erpnext": "15.119.3"}
		with mock.patch.dict(compatibility._installed_versions, fake):
			with self.assertRaisesRegex(frappe.exceptions.ValidationError, r"version-15"):
				compatibility.validate_runtime_compatibility()

	def test_erpnext_below_supported_floor_is_rejected(self):
		import unittest.mock as mock

		from vellox_agency import compatibility

		fake = {"frappe": "15.118.0", "erpnext": "15.100.0"}
		with mock.patch.dict(compatibility._installed_versions, fake):
			with self.assertRaisesRegex(frappe.exceptions.ValidationError, r"15\.119\.1"):
				compatibility.validate_runtime_compatibility()


def test_deliberate_ci_failure_probe():
	assert False, "deliberate failure: proving CI catches broken tests"
