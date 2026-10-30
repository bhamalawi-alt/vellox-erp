import json

import frappe
from frappe.tests.utils import FrappeTestCase

WORKSPACE_PATH = ("vellox_agency_reports", "workspace", "vellox_agency", "vellox_agency.json")


class TestVelloxAgencyWorkspace(FrappeTestCase):
	def test_shortcut_stats_filters_use_existing_fields(self):
		with open(frappe.get_app_path("vellox_agency", *WORKSPACE_PATH)) as f:
			workspace = json.load(f)

		for shortcut in workspace["shortcuts"]:
			if not shortcut.get("stats_filter"):
				continue
			meta = frappe.get_meta(shortcut["link_to"])
			for fieldname in json.loads(shortcut["stats_filter"]):
				with self.subTest(shortcut=shortcut["label"], field=fieldname):
					self.assertTrue(
						meta.has_field(fieldname) or fieldname in frappe.model.default_fields,
						f"{shortcut['link_to']} has no field '{fieldname}'",
					)
