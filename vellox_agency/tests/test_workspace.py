import json

import frappe
from frappe.tests.utils import FrappeTestCase

from vellox_agency.deprecations import DEPRECATION_TARGETS, LEGACY_REPORTS

WORKSPACE_PATH = ("vellox_agency_reports", "workspace", "vellox_agency", "vellox_agency.json")

# First-generation prototype modules: empty controllers, never built out.
PROTOTYPE_DOCTYPES = {"Agency Campaign", "Production Job", "Capacity Plan", "Skill"}


def _workspace():
	with open(frappe.get_app_path("vellox_agency", *WORKSPACE_PATH)) as f:
		return json.load(f)


def _doctype_targets(workspace):
	"""(label, DocType) for every shortcut and link that opens a DocType."""
	targets = [(s["label"], s["link_to"]) for s in workspace["shortcuts"] if s.get("type") == "DocType"]
	targets += [
		(link["label"], link["link_to"])
		for link in workspace["links"]
		if link.get("type") == "Link" and link.get("link_type") == "DocType"
	]
	return targets


class TestVelloxAgencyWorkspace(FrappeTestCase):
	def test_shortcut_stats_filters_use_existing_fields(self):
		for shortcut in _workspace()["shortcuts"]:
			if not shortcut.get("stats_filter"):
				continue
			meta = frappe.get_meta(shortcut["link_to"])
			for fieldname in json.loads(shortcut["stats_filter"]):
				with self.subTest(shortcut=shortcut["label"], field=fieldname):
					self.assertTrue(
						meta.has_field(fieldname) or fieldname in frappe.model.default_fields,
						f"{shortcut['link_to']} has no field '{fieldname}'",
					)

	def test_menu_opens_only_live_record_types(self):
		retired = set(DEPRECATION_TARGETS) | PROTOTYPE_DOCTYPES
		for label, doctype in _doctype_targets(_workspace()):
			with self.subTest(entry=label, doctype=doctype):
				self.assertTrue(frappe.db.exists("DocType", doctype), f"{doctype} does not exist")
				self.assertNotIn(doctype, retired, f"'{label}' opens retired record type {doctype}")

	def test_menu_covers_the_erpnext_records_staff_use(self):
		opened = {doctype for _, doctype in _doctype_targets(_workspace())}
		for doctype in ("Customer", "Project", "Timesheet", "Sales Invoice", "Quotation", "Item"):
			with self.subTest(doctype=doctype):
				self.assertIn(doctype, opened)

	def test_legacy_reports_are_hidden(self):
		linked = {link["link_to"] for link in _workspace()["links"] if link.get("link_type") == "Report"}
		self.assertFalse(linked & set(LEGACY_REPORTS), f"menu still links {linked & set(LEGACY_REPORTS)}")
		for report in LEGACY_REPORTS:
			with self.subTest(report=report):
				self.assertEqual(frappe.db.get_value("Report", report, "disabled"), 1)

	def test_patch_disables_legacy_reports_on_existing_sites(self):
		# Frappe's file sync never overwrites a Report's "disabled" flag on an
		# existing site, so the patch is what hides them there.
		from vellox_agency.patches.disable_legacy_reports import execute

		for report in LEGACY_REPORTS:
			frappe.db.set_value("Report", report, "disabled", 0)
		execute()
		execute()  # idempotent
		for report in LEGACY_REPORTS:
			with self.subTest(report=report):
				self.assertEqual(frappe.db.get_value("Report", report, "disabled"), 1)

	def test_layout_blocks_match_shortcuts_and_cards(self):
		workspace = _workspace()
		shortcuts = {s["label"] for s in workspace["shortcuts"]}
		cards = {link["label"] for link in workspace["links"] if link.get("type") == "Card Break"}
		for block in json.loads(workspace["content"]):
			data = block.get("data", {})
			if block["type"] == "shortcut":
				self.assertIn(data["shortcut_name"], shortcuts)
			elif block["type"] == "card":
				self.assertIn(data["card_name"], cards)
