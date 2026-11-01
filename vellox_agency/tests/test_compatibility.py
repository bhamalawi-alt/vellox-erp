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

	def _fake(self, **versions):
		import unittest.mock as mock

		from vellox_agency import compatibility

		base = {"frappe": "15.125.0", "erpnext": "15.124.3", "hrms": compatibility.TESTED_VERSIONS["hrms"]}
		return mock.patch.dict(compatibility._installed_versions, {**base, **versions})

	def test_frappe_hr_is_required(self):
		# [P4-102]: staff, leave and holidays live in Frappe HR (capacity plan, P4-29).
		self.assertIn("hrms", frappe.get_hooks("required_apps", app_name="vellox_agency"))

	def test_missing_frappe_hr_is_rejected_with_the_install_command(self):
		from vellox_agency import compatibility

		with self._fake(hrms=""), self.assertRaisesRegex(frappe.exceptions.ValidationError, "get-app hrms"):
			compatibility.validate_runtime_compatibility()

	def test_frappe_hr_outside_the_supported_range_is_rejected(self):
		from vellox_agency import compatibility

		for version in ("16.0.0", "14.20.0"):
			with self.subTest(version=version), self._fake(hrms=version):
				with self.assertRaisesRegex(frappe.exceptions.ValidationError, "hrms"):
					compatibility.validate_runtime_compatibility()

	def test_the_tested_frappe_hr_passes(self):
		from vellox_agency import compatibility

		with self._fake():
			compatibility.validate_runtime_compatibility()


def test_deliberate_ci_failure_probe():
	assert False, "deliberate failure: proving CI catches broken tests"
