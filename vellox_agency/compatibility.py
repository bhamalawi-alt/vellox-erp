"""Runtime compatibility gate for the vellox_agency app.

Declares the supported Frappe / ERPNext / Frappe HR (hrms) v15 ranges, verified
against the delivery benches (TESTED_VERSIONS; ERPNext 15.119.1 was verified
during the 2026-08-14 audit). Frappe HR is required from [P4-102]: staff,
holidays and leave live there (capacity plan, P4-29). v16 is out of scope for
this release.
"""

import frappe
from frappe.exceptions import ValidationError
from packaging.specifiers import SpecifierSet
from packaging.version import Version

FRAPPE_SUPPORTED = ">=15.118.0,<16"
ERPNEXT_SUPPORTED = ">=15.119.1,<16"
HRMS_SUPPORTED = ">=15.64.0,<16"

TESTED_VERSIONS = {"frappe": "15.125.0", "erpnext": "15.124.3", "hrms": "15.64.7"}

_installed_versions: dict[str, str] = {}


def _version(app: str) -> str:
	if app in _installed_versions:
		return _installed_versions[app]
	from importlib.metadata import PackageNotFoundError
	from importlib.metadata import version as dist_version

	try:
		return dist_version(app)
	except PackageNotFoundError:
		return ""


def _check(app: str, specifier: str) -> None:
	current = _version(app)
	if not current:
		raise ValidationError(
			f"App '{app}' is required by vellox_agency but is not installed. "
			f"Install it with: bench get-app {app} --branch version-15"
		)
	if Version(current) not in SpecifierSet(specifier):
		raise ValidationError(
			f"{app} {current} is not supported by vellox_agency. "
			f"Supported range: {specifier}. "
			f"Switch with: bench switch-to-branch version-15 {app} && bench update. "
			f"Frappe/ERPNext v16 support is planned for a future release."
		)


def validate_runtime_compatibility() -> None:
	_check("frappe", FRAPPE_SUPPORTED)
	_check("erpnext", ERPNEXT_SUPPORTED)
	_check("hrms", HRMS_SUPPORTED)
