# Vellox Technical and Financial Offer Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Vellox staff select a client and service Items on an ERPNext Quotation, generate an editable technical proposal from the selected services, and print technical, financial, or combined offers.

**Architecture:** Extend ERPNext `Item` and `Quotation` through idempotent custom fields owned by `vellox_agency`. A small permission-aware Python service composes proposal HTML, a Desk JavaScript extension manages regeneration and stale-state warnings, and three standard Jinja Print Formats render the outputs. ERPNext remains authoritative for clients, services, EGP/USD prices, taxes, discounts, totals, validity, and submission.

**Tech Stack:** Frappe Framework 15.118.0, ERPNext 15.119.1, Python 3.11, Frappe Desk JavaScript, Jinja Print Formats, Frappe integration tests, Node's built-in test runner.

## Global Constraints

- The app version remains `vellox_agency` 0.0.1 during this feature.
- ERPNext `Customer`, `Contact`, `Address`, `Item`, `Item Price`, and `Quotation` remain authoritative.
- Supported transaction currencies are EGP and USD; no custom price engine is introduced.
- Do not modify files under the upstream `frappe` or `erpnext` apps.
- Do not add a parallel Offer, Client, Service, or Financial Offer DocType.
- The Quotation receives one visible Vellox field: `custom_vellox_technical_proposal`.
- The hidden `custom_vellox_proposal_item_signature` field is allowed only for stale-state detection.
- Service configuration is shown only for non-stock Items.
- Generated proposal text never overwrites edited text without explicit confirmation.
- English print labels must preserve Arabic rich text entered by users.
- Social media, AI writing, translation, electronic signatures, client portal, new approval workflows, contract creation, Project creation, and milestone generation remain out of scope.
- Every Python behavior change follows a failing Frappe test first; pure JavaScript state behavior follows a failing `node --test` first.

## Local Bench Sync Rule

> Updated 2026-08-25 by [P0-02]: the repository was flattened so the root is the
> installable app. Sync the repository root instead of the old nested path.

The active preview bench uses a copied app at `/private/tmp/vellox-frappe-bench/apps/vellox_agency`, not a symlink to this repository. Immediately before every bench migration, build, or test command in this plan, sync the current repository app with:

```bash
rsync -a --exclude "__pycache__" --exclude "*.pyc" --exclude ".git" \
  --exclude ".bench-venv" --exclude "frappe-bench" \
  --exclude "docs" --exclude "scripts" \
"/Users/imac/Documents/ChatGPT/vellox erp/Elyostudio/" \
"/private/tmp/vellox-frappe-bench/apps/vellox_agency/"
```

This command intentionally does not use `--delete`; it must not remove unrelated files from the active local bench.

---

### Task 1: Idempotent Offer-Builder Metadata

**Files:**
- Create: `apps/vellox_agency/vellox_agency/setup/__init__.py`
- Create: `apps/vellox_agency/vellox_agency/setup/offer_builder.py`
- Create: `apps/vellox_agency/vellox_agency/tests/__init__.py`
- Create: `apps/vellox_agency/vellox_agency/tests/test_offer_builder_setup.py`
- Modify: `apps/vellox_agency/vellox_agency/install.py`
- Modify: `apps/vellox_agency/vellox_agency/hooks.py`

**Interfaces:**
- Produces: `get_offer_builder_custom_fields() -> dict[str, list[dict]]`
- Produces: `setup_offer_builder() -> None`
- Later tasks consume the six exact fieldnames defined here.

- [ ] **Step 1: Write the failing metadata test**

Create the test package and `test_offer_builder_setup.py`:

```python
import importlib

import frappe
from frappe.tests.utils import FrappeTestCase


class TestOfferBuilderSetup(FrappeTestCase):
	def test_custom_field_contract(self):
		try:
			module = importlib.import_module("vellox_agency.setup.offer_builder")
		except ModuleNotFoundError:
			self.fail("vellox_agency.setup.offer_builder must define the offer metadata")

		fields = module.get_offer_builder_custom_fields()
		self.assertEqual(
			[field["fieldname"] for field in fields["Item"]],
			[
				"custom_vellox_technical_proposal",
				"custom_vellox_default_duration",
				"custom_vellox_billing_method",
				"custom_vellox_project_template",
			],
		)
		self.assertEqual(
			[field["fieldname"] for field in fields["Quotation"]],
			[
				"custom_vellox_technical_proposal",
				"custom_vellox_proposal_item_signature",
			],
		)

	def test_setup_is_idempotent(self):
		module = importlib.import_module("vellox_agency.setup.offer_builder")
		module.setup_offer_builder()
		module.setup_offer_builder()

		self.assertEqual(
			frappe.get_meta("Item", cached=False).get_field("custom_vellox_billing_method").options,
			"Fixed Price\nMilestone\nRetainer\nTime and Materials",
		)
		self.assertEqual(
			frappe.get_meta("Quotation", cached=False)
			.get_field("custom_vellox_technical_proposal")
			.fieldtype,
			"Text Editor",
		)
```

- [ ] **Step 2: Run the test and confirm the intended failure**

Run the Local Bench Sync Rule, then from `/private/tmp/vellox-frappe-bench` run:

```bash
"/Users/imac/Documents/ChatGPT/vellox erp/Elyostudio/.bench-venv/bin/bench" --site vellox.localhost run-tests --app vellox_agency --module vellox_agency.tests.test_offer_builder_setup
```

Expected: FAIL because `vellox_agency.setup.offer_builder` does not exist.

- [ ] **Step 3: Implement the metadata contract**

Create `setup/__init__.py` as an empty package marker. Create `setup/offer_builder.py`:

```python
from copy import deepcopy

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


OFFER_BUILDER_CUSTOM_FIELDS = {
	"Item": [
		{
			"fieldname": "custom_vellox_technical_proposal",
			"label": "Technical Proposal Template",
			"fieldtype": "Text Editor",
			"insert_after": "description",
			"depends_on": "eval:doc.is_stock_item == 0",
		},
		{
			"fieldname": "custom_vellox_default_duration",
			"label": "Default Duration",
			"fieldtype": "Data",
			"insert_after": "custom_vellox_technical_proposal",
			"depends_on": "eval:doc.is_stock_item == 0",
		},
		{
			"fieldname": "custom_vellox_billing_method",
			"label": "Billing Method",
			"fieldtype": "Select",
			"options": "Fixed Price\nMilestone\nRetainer\nTime and Materials",
			"insert_after": "custom_vellox_default_duration",
			"depends_on": "eval:doc.is_stock_item == 0",
		},
		{
			"fieldname": "custom_vellox_project_template",
			"label": "Project Template",
			"fieldtype": "Link",
			"options": "Project Template",
			"insert_after": "custom_vellox_billing_method",
			"depends_on": "eval:doc.is_stock_item == 0",
		},
	],
	"Quotation": [
		{
			"fieldname": "custom_vellox_technical_proposal",
			"label": "Technical Proposal",
			"fieldtype": "Text Editor",
			"insert_after": "terms",
		},
		{
			"fieldname": "custom_vellox_proposal_item_signature",
			"label": "Proposal Item Signature",
			"fieldtype": "Small Text",
			"insert_after": "custom_vellox_technical_proposal",
			"hidden": 1,
			"read_only": 1,
			"no_copy": 1,
		},
	],
}


def get_offer_builder_custom_fields():
	return deepcopy(OFFER_BUILDER_CUSTOM_FIELDS)


def setup_offer_builder():
	create_custom_fields(get_offer_builder_custom_fields(), update=True)
```

Update `install.py`:

```python
from vellox_agency.setup.offer_builder import setup_offer_builder


def after_install():
	for role in AGENCY_ROLES:
		create_role(role)
	setup_offer_builder()
```

Activate the ERPNext dependency and migration hook in `hooks.py`:

```python
required_apps = ["erpnext"]
after_migrate = "vellox_agency.setup.offer_builder.setup_offer_builder"
```

- [ ] **Step 4: Run the metadata test and full app tests**

Run the Local Bench Sync Rule, run the Task 1 test command again, then:

```bash
"/Users/imac/Documents/ChatGPT/vellox erp/Elyostudio/.bench-venv/bin/bench" --site vellox.localhost run-tests --app vellox_agency
```

Expected: PASS with the custom-field contract present and idempotent.

- [ ] **Step 5: Commit Task 1**

```bash
git add apps/vellox_agency/vellox_agency/setup apps/vellox_agency/vellox_agency/tests apps/vellox_agency/vellox_agency/install.py apps/vellox_agency/vellox_agency/hooks.py
git commit -m "feat: add offer builder metadata"
```

---

### Task 2: Permission-Aware Proposal Composition

**Files:**
- Create: `apps/vellox_agency/vellox_agency/offer_builder/__init__.py`
- Create: `apps/vellox_agency/vellox_agency/offer_builder/proposal.py`
- Create: `apps/vellox_agency/vellox_agency/tests/test_offer_builder.py`

**Interfaces:**
- Produces: `get_item_signature(item_codes: list[str]) -> str`
- Produces: `compose_technical_proposal(item_codes: list[str]) -> dict`
- Produces: whitelisted `build_technical_proposal(quotation: str | dict) -> dict`
- Response keys are exactly `html`, `item_signature`, and `skipped_items`.

- [ ] **Step 1: Write failing proposal-composition tests**

Create `test_offer_builder.py`:

```python
import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext.selling.doctype.quotation.test_quotation import make_quotation
from erpnext.stock.doctype.item.test_item import make_item
from vellox_agency.setup.offer_builder import setup_offer_builder


class TestOfferBuilder(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_offer_builder()

	def setUp(self):
		super().setUp()
		self.strategy = self.make_service(
			"_Test Vellox Strategy",
			"<p>Strategy proposal body</p>",
			duration="6 weeks",
			billing_method="Fixed Price",
		)
		self.design = self.make_service(
			"_Test Vellox Design",
			"<p>Design proposal body</p>",
			billing_method="Milestone",
		)

	def make_service(self, item_code, proposal, duration=None, billing_method=None):
		item = make_item(item_code, {"is_stock_item": 0})
		item.custom_vellox_technical_proposal = proposal
		item.custom_vellox_default_duration = duration
		item.custom_vellox_billing_method = billing_method
		item.save()
		return item

	def test_composes_unique_sections_in_item_order(self):
		from vellox_agency.offer_builder.proposal import compose_technical_proposal

		result = compose_technical_proposal(
			[self.strategy.name, self.design.name, self.strategy.name]
		)
		self.assertLess(result["html"].index("Strategy proposal body"), result["html"].index("Design proposal body"))
		self.assertEqual(result["html"].count("Strategy proposal body"), 1)
		self.assertIn("6 weeks", result["html"])
		self.assertIn("Fixed Price", result["html"])
		self.assertNotIn("None", result["html"])
		self.assertEqual(result["item_signature"], '["_Test Vellox Strategy","_Test Vellox Design"]')

	def test_reports_service_without_template(self):
		from vellox_agency.offer_builder.proposal import compose_technical_proposal

		empty = self.make_service("_Test Vellox Empty", "")
		result = compose_technical_proposal([empty.name, self.design.name])
		self.assertEqual(result["skipped_items"], [empty.item_name])
		self.assertIn("Design proposal body", result["html"])

	def test_rejects_generation_when_no_service_has_a_template(self):
		from vellox_agency.offer_builder.proposal import compose_technical_proposal

		empty = self.make_service("_Test Vellox No Proposal", "")
		with self.assertRaisesRegex(frappe.ValidationError, "No selected service has a Technical Proposal Template"):
			compose_technical_proposal([empty.name])

	def test_rejects_submitted_quotation(self):
		from vellox_agency.offer_builder.proposal import build_technical_proposal

		quotation = make_quotation(
			item=self.strategy.name,
			rate=100,
			do_not_submit=False,
		)
		with self.assertRaisesRegex(frappe.ValidationError, "draft Quotation"):
			build_technical_proposal(quotation.as_dict())

	def test_rejects_guest_user(self):
		from vellox_agency.offer_builder.proposal import build_technical_proposal

		quotation = make_quotation(item=self.strategy.name, rate=100, do_not_submit=True)
		with self.set_user("Guest"), self.assertRaises(frappe.PermissionError):
			build_technical_proposal(quotation.as_dict())

	def test_generation_preserves_egp_and_usd_financial_values(self):
		from vellox_agency.offer_builder.proposal import build_technical_proposal

		for currency, rate in (("EGP", 5000), ("USD", 100)):
			with self.subTest(currency=currency):
				quotation = make_quotation(
					item=self.strategy.name,
					rate=rate,
					currency=currency,
					do_not_save=True,
				)
				quotation.conversion_rate = 1
				quotation.price_list_currency = currency
				quotation.plc_conversion_rate = 1
				quotation.calculate_taxes_and_totals()
				financial_before = (quotation.currency, quotation.items[0].rate, quotation.grand_total)

				build_technical_proposal(quotation.as_dict())

				self.assertEqual(
					(quotation.currency, quotation.items[0].rate, quotation.grand_total),
					financial_before,
				)
```

- [ ] **Step 2: Run the tests and confirm the intended failure**

Run the Local Bench Sync Rule, then run:

```bash
"/Users/imac/Documents/ChatGPT/vellox erp/Elyostudio/.bench-venv/bin/bench" --site vellox.localhost run-tests --app vellox_agency --module vellox_agency.tests.test_offer_builder
```

Expected: FAIL because `vellox_agency.offer_builder.proposal` does not exist.

- [ ] **Step 3: Implement the proposal service**

Create the package marker and `offer_builder/proposal.py`:

```python
import json
from html import escape

import frappe
from frappe import _
from frappe.utils import cint, sanitize_html


def _unique_item_codes(item_codes):
	return list(dict.fromkeys(code for code in item_codes if code))


def get_item_signature(item_codes):
	return json.dumps(_unique_item_codes(item_codes), ensure_ascii=False, separators=(",", ":"))


def compose_technical_proposal(item_codes):
	sections = []
	skipped_items = []
	unique_codes = _unique_item_codes(item_codes)

	for item_code in unique_codes:
		item = frappe.get_doc("Item", item_code)
		item.check_permission("read")
		template = item.custom_vellox_technical_proposal or ""
		if not template.strip():
			skipped_items.append(item.item_name)
			continue

		metadata = []
		if item.custom_vellox_default_duration:
			metadata.append(
				f'<span><strong>{escape(_("Duration"))}:</strong> '
				f'{escape(item.custom_vellox_default_duration)}</span>'
			)
		if item.custom_vellox_billing_method:
			metadata.append(
				f'<span><strong>{escape(_("Billing Method"))}:</strong> '
				f'{escape(item.custom_vellox_billing_method)}</span>'
			)

		metadata_html = ""
		if metadata:
			metadata_html = f'<div class="vellox-service-meta">{" &middot; ".join(metadata)}</div>'

		sections.append(
			'<section class="vellox-service-proposal">'
			f"<h2>{escape(item.item_name)}</h2>"
			f"{metadata_html}"
			f'<div class="vellox-service-body">{sanitize_html(template, linkify=True)}</div>'
			"</section>"
		)

	if not sections:
		frappe.throw(_("No selected service has a Technical Proposal Template."))

	return {
		"html": "".join(sections),
		"item_signature": get_item_signature(unique_codes),
		"skipped_items": skipped_items,
	}


def _check_quotation_permission(quotation):
	if cint(quotation.get("docstatus")) != 0:
		frappe.throw(_("Technical proposals can only be generated for a draft Quotation."))

	name = quotation.get("name")
	if name and not str(name).startswith("new-") and frappe.db.exists("Quotation", name):
		stored = frappe.get_doc("Quotation", name)
		stored.check_permission("write")
		if stored.docstatus != 0:
			frappe.throw(_("Technical proposals can only be generated for a draft Quotation."))
		return

	if not frappe.has_permission("Quotation", "create"):
		frappe.throw(_("You are not permitted to create a Quotation."), frappe.PermissionError)


@frappe.whitelist()
def build_technical_proposal(quotation):
	quotation = frappe.parse_json(quotation)
	if quotation.get("doctype") != "Quotation":
		frappe.throw(_("A Quotation is required."))

	_check_quotation_permission(quotation)
	return compose_technical_proposal(
		[row.get("item_code") for row in quotation.get("items") or []]
	)
```

- [ ] **Step 4: Run the focused and full Python tests**

Run the Local Bench Sync Rule, then run the Task 2 command followed by the full app test command from Task 1.

Expected: all focused tests and all `vellox_agency` tests PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add apps/vellox_agency/vellox_agency/offer_builder apps/vellox_agency/vellox_agency/tests/test_offer_builder.py
git commit -m "feat: compose service technical proposals"
```

---

### Task 3: Quotation Desk Interaction

**Files:**
- Create: `apps/vellox_agency/vellox_agency/public/js/quotation_offer_builder.js`
- Create: `apps/vellox_agency/vellox_agency/tests/js/test_quotation_offer_builder.js`
- Modify: `apps/vellox_agency/vellox_agency/hooks.py`

**Interfaces:**
- Consumes: `vellox_agency.offer_builder.proposal.build_technical_proposal`
- Produces: `getItemSignature(doc) -> string`
- Produces: `isProposalStale(doc) -> boolean`

- [ ] **Step 1: Write failing JavaScript state tests**

Create `tests/js/test_quotation_offer_builder.js`:

```javascript
const test = require("node:test");
const assert = require("node:assert/strict");
const {
	getItemSignature,
	isProposalStale,
} = require("../../public/js/quotation_offer_builder.js");

test("signature preserves first service order and removes duplicates", () => {
	const doc = {
		items: [
			{ item_code: "Strategy" },
			{ item_code: "Design" },
			{ item_code: "Strategy" },
		],
	};
	assert.equal(getItemSignature(doc), '["Strategy","Design"]');
});

test("proposal is stale only when generated services change", () => {
	const doc = {
		items: [{ item_code: "Strategy", qty: 2 }],
		custom_vellox_technical_proposal: "<p>Edited proposal</p>",
		custom_vellox_proposal_item_signature: '["Strategy"]',
	};
	assert.equal(isProposalStale(doc), false);
	doc.items[0].qty = 9;
	assert.equal(isProposalStale(doc), false);
	doc.items.push({ item_code: "Design", qty: 1 });
	assert.equal(isProposalStale(doc), true);
});
```

- [ ] **Step 2: Run the JavaScript test and confirm the intended failure**

From the repository root, run:

```bash
node --test apps/vellox_agency/vellox_agency/tests/js/test_quotation_offer_builder.js
```

Expected: FAIL because `quotation_offer_builder.js` does not exist.

- [ ] **Step 3: Implement the Quotation extension**

Create `public/js/quotation_offer_builder.js`:

```javascript
function getItemCodes(doc) {
	return [...new Set((doc.items || []).map((row) => row.item_code).filter(Boolean))];
}

function getItemSignature(doc) {
	return JSON.stringify(getItemCodes(doc));
}

function isProposalStale(doc) {
	return Boolean(
		doc.custom_vellox_technical_proposal &&
			doc.custom_vellox_proposal_item_signature &&
			doc.custom_vellox_proposal_item_signature !== getItemSignature(doc)
	);
}

function confirmRegeneration(frm) {
	if (!frm.doc.custom_vellox_technical_proposal) {
		return Promise.resolve(true);
	}
	return new Promise((resolve) => {
		frappe.confirm(
			__("Rebuild the Technical Proposal and replace the current edited text?"),
			() => resolve(true),
			() => resolve(false)
		);
	});
}

function updateProposalDescription(frm) {
	const description = isProposalStale(frm.doc)
		? __("The selected services changed. Rebuild the Technical Proposal when you are ready to replace its current text.")
		: __("Generated from the selected service Items and editable for this client.");
	frm.set_df_property("custom_vellox_technical_proposal", "description", description);
}

async function buildTechnicalProposal(frm) {
	if (!(await confirmRegeneration(frm))) {
		return;
	}

	const response = await frappe.call({
		method: "vellox_agency.offer_builder.proposal.build_technical_proposal",
		args: { quotation: frm.doc },
		freeze: true,
		freeze_message: __("Building Technical Proposal"),
	});
	const result = response.message;
	await frm.set_value("custom_vellox_technical_proposal", result.html);
	await frm.set_value("custom_vellox_proposal_item_signature", result.item_signature);
	updateProposalDescription(frm);

	if (result.skipped_items.length) {
		frappe.msgprint({
			title: __("Proposal Built"),
			indicator: "orange",
			message: __("These services have no Technical Proposal Template and were skipped: {0}", [
				frappe.utils.escape_html(result.skipped_items.join(", ")),
			]),
		});
	}
}

if (typeof module !== "undefined") {
	module.exports = { getItemSignature, isProposalStale };
}

if (typeof frappe !== "undefined") {
	frappe.ui.form.on("Quotation", {
		refresh(frm) {
			updateProposalDescription(frm);
			if (frm.doc.docstatus === 0 && frm.has_perm("write") && getItemCodes(frm.doc).length) {
				frm.add_custom_button(__("Build Technical Proposal"), () => buildTechnicalProposal(frm));
			}
		},
	});

	frappe.ui.form.on("Quotation Item", {
		item_code(frm) {
			updateProposalDescription(frm);
		},
		items_remove(frm) {
			updateProposalDescription(frm);
		},
	});
}
```

Register the script in `hooks.py`:

```python
doctype_js = {"Quotation": "public/js/quotation_offer_builder.js"}
```

- [ ] **Step 4: Run JavaScript tests and build assets**

Run the Task 3 Node test, run the Local Bench Sync Rule, then from `/private/tmp/vellox-frappe-bench` run:

```bash
"/Users/imac/Documents/ChatGPT/vellox erp/Elyostudio/.bench-venv/bin/bench" build --app vellox_agency
```

Expected: Node tests PASS and the asset build exits 0.

- [ ] **Step 5: Commit Task 3**

```bash
git add apps/vellox_agency/vellox_agency/public/js/quotation_offer_builder.js apps/vellox_agency/vellox_agency/tests/js/test_quotation_offer_builder.js apps/vellox_agency/vellox_agency/hooks.py
git commit -m "feat: add quotation proposal builder controls"
```

---

### Task 4: Branded Technical, Financial, and Combined Print Formats

**Files:**
- Create: `apps/vellox_agency/vellox_agency/templates/print_formats/offer.css`
- Create: `apps/vellox_agency/vellox_agency/templates/print_formats/offer_header.html`
- Create: `apps/vellox_agency/vellox_agency/templates/print_formats/financial_section.html`
- Create: `apps/vellox_agency/vellox_agency/templates/print_formats/technical_offer.html`
- Create: `apps/vellox_agency/vellox_agency/templates/print_formats/financial_offer.html`
- Create: `apps/vellox_agency/vellox_agency/templates/print_formats/combined_offer.html`
- Create: `apps/vellox_agency/vellox_agency/vellox_agency_crm/print_format/vellox_technical_offer/vellox_technical_offer.json`
- Create: `apps/vellox_agency/vellox_agency/vellox_agency_crm/print_format/vellox_financial_offer/vellox_financial_offer.json`
- Create: `apps/vellox_agency/vellox_agency/vellox_agency_crm/print_format/vellox_combined_offer/vellox_combined_offer.json`
- Create: `apps/vellox_agency/vellox_agency/tests/test_offer_print_formats.py`

**Interfaces:**
- Consumes: standard Quotation fields and `custom_vellox_technical_proposal`.
- Produces: Print Formats named `Vellox Technical Offer`, `Vellox Financial Offer`, and `Vellox Combined Offer`.

- [ ] **Step 1: Write failing Print Format tests**

Create `test_offer_print_formats.py`:

```python
import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext.selling.doctype.quotation.test_quotation import make_quotation
from erpnext.stock.doctype.item.test_item import make_item
from vellox_agency.setup.offer_builder import setup_offer_builder


class TestOfferPrintFormats(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_offer_builder()

	def test_three_offer_formats_render_expected_sections(self):
		item = make_item("_Test Vellox Print Service", {"is_stock_item": 0})
		quotation = make_quotation(item=item.name, rate=2500, do_not_submit=True)
		quotation.custom_vellox_technical_proposal = "<p>Client-specific technical content</p>"
		quotation.save()

		technical = frappe.get_print("Quotation", quotation.name, "Vellox Technical Offer", no_letterhead=1)
		financial = frappe.get_print("Quotation", quotation.name, "Vellox Financial Offer", no_letterhead=1)
		combined = frappe.get_print("Quotation", quotation.name, "Vellox Combined Offer", no_letterhead=1)

		self.assertIn("Client-specific technical content", technical)
		self.assertNotIn("Grand Total", technical)
		self.assertIn(item.item_name, financial)
		self.assertIn("Grand Total", financial)
		self.assertNotIn("Client-specific technical content", financial)
		self.assertIn("Client-specific technical content", combined)
		self.assertIn("Grand Total", combined)
```

- [ ] **Step 2: Run the Print Format test and confirm the intended failure**

Run the Local Bench Sync Rule, then run:

```bash
"/Users/imac/Documents/ChatGPT/vellox erp/Elyostudio/.bench-venv/bin/bench" --site vellox.localhost run-tests --app vellox_agency --module vellox_agency.tests.test_offer_print_formats
```

Expected: FAIL because the three Vellox Print Formats do not exist.

- [ ] **Step 3: Create the shared print templates**

Create `offer.css`:

```css
.vellox-offer { color: #172033; font-size: 10pt; }
.vellox-offer h1 { font-size: 24pt; margin: 0 0 18px; }
.vellox-offer h2 { font-size: 15pt; margin: 22px 0 8px; }
.vellox-offer-meta { display: flex; justify-content: space-between; margin-bottom: 22px; }
.vellox-offer-client { background: #f4f6fa; padding: 14px; margin-bottom: 24px; }
.vellox-service-meta { color: #596579; margin-bottom: 8px; }
.vellox-financial-table { width: 100%; border-collapse: collapse; }
.vellox-financial-table th, .vellox-financial-table td { border-bottom: 1px solid #dfe3eb; padding: 8px; }
.vellox-financial-table .number { text-align: right; }
.vellox-total-row td { font-weight: 700; border-top: 2px solid #172033; }
.vellox-page-break { page-break-before: always; }
```

Create `offer_header.html`:

```html
<style>{% include "vellox_agency/templates/print_formats/offer.css" %}</style>
<div class="vellox-offer">
	{% if letter_head %}{{ letter_head }}{% endif %}
	<h1>{{ offer_heading }}</h1>
	<div class="vellox-offer-meta">
		<span><strong>{{ _("Offer") }}:</strong> {{ doc.name }}</span>
		<span><strong>{{ _("Date") }}:</strong> {{ doc.get_formatted("transaction_date") }}</span>
		{% if doc.valid_till %}<span><strong>{{ _("Valid Until") }}:</strong> {{ doc.get_formatted("valid_till") }}</span>{% endif %}
	</div>
	<div class="vellox-offer-client">
		<strong>{{ doc.customer_name or doc.party_name }}</strong>
		{% if doc.contact_display %}<div>{{ doc.contact_display }}</div>{% endif %}
		{% if doc.address_display %}<div>{{ doc.address_display }}</div>{% endif %}
	</div>
```

Create `financial_section.html`:

```html
<table class="vellox-financial-table">
	<thead><tr><th>{{ _("Service") }}</th><th class="number">{{ _("Qty") }}</th><th class="number">{{ _("Rate") }}</th><th class="number">{{ _("Amount") }}</th></tr></thead>
	<tbody>
	{% for row in doc.items %}
		<tr><td>{{ row.item_name }}</td><td class="number">{{ row.get_formatted("qty", doc) }}</td><td class="number">{{ row.get_formatted("rate", doc) }}</td><td class="number">{{ row.get_formatted("amount", doc) }}</td></tr>
	{% endfor %}
	{% for tax in doc.taxes %}
		<tr><td colspan="3" class="number">{{ tax.description }}</td><td class="number">{{ tax.get_formatted("tax_amount", doc) }}</td></tr>
	{% endfor %}
	{% if doc.discount_amount %}
		<tr><td colspan="3" class="number">{{ _("Discount") }}</td><td class="number">-{{ doc.get_formatted("discount_amount") }}</td></tr>
	{% endif %}
		<tr class="vellox-total-row"><td colspan="3" class="number">{{ _("Grand Total") }} ({{ doc.currency }})</td><td class="number">{{ doc.get_formatted("grand_total") }}</td></tr>
	</tbody>
</table>
{% if doc.in_words %}<p><strong>{{ _("In Words") }}:</strong> {{ doc.in_words }}</p>{% endif %}
{% if doc.terms %}<h2>{{ _("Commercial Terms") }}</h2><div>{{ doc.terms }}</div>{% endif %}
```

Create `technical_offer.html`:

```html
{% set offer_heading = _("Technical Offer") %}
{% include "vellox_agency/templates/print_formats/offer_header.html" %}
<div class="vellox-technical-content">{{ doc.custom_vellox_technical_proposal or "" }}</div>
</div>
```

Create `financial_offer.html`:

```html
{% set offer_heading = _("Financial Offer") %}
{% include "vellox_agency/templates/print_formats/offer_header.html" %}
{% include "vellox_agency/templates/print_formats/financial_section.html" %}
</div>
```

Create `combined_offer.html`:

```html
{% set offer_heading = _("Technical and Financial Offer") %}
{% include "vellox_agency/templates/print_formats/offer_header.html" %}
<div class="vellox-technical-content">{{ doc.custom_vellox_technical_proposal or "" }}</div>
<div class="vellox-page-break"></div>
<h1>{{ _("Financial Offer") }}</h1>
{% include "vellox_agency/templates/print_formats/financial_section.html" %}
</div>
```

- [ ] **Step 4: Create the three standard Print Format JSON records**

Create the Technical record:

```json
{"custom_format":1,"disabled":0,"doc_type":"Quotation","docstatus":0,"doctype":"Print Format","html":"{% include \"vellox_agency/templates/print_formats/technical_offer.html\" %}","module":"Vellox Agency CRM","name":"Vellox Technical Offer","print_format_builder":0,"print_format_type":"Jinja","raw_printing":0,"standard":"Yes"}
```

Create the Financial record:

```json
{"custom_format":1,"disabled":0,"doc_type":"Quotation","docstatus":0,"doctype":"Print Format","html":"{% include \"vellox_agency/templates/print_formats/financial_offer.html\" %}","module":"Vellox Agency CRM","name":"Vellox Financial Offer","print_format_builder":0,"print_format_type":"Jinja","raw_printing":0,"standard":"Yes"}
```

Create the Combined record:

```json
{"custom_format":1,"disabled":0,"doc_type":"Quotation","docstatus":0,"doctype":"Print Format","html":"{% include \"vellox_agency/templates/print_formats/combined_offer.html\" %}","module":"Vellox Agency CRM","name":"Vellox Combined Offer","print_format_builder":0,"print_format_type":"Jinja","raw_printing":0,"standard":"Yes"}
```

- [ ] **Step 5: Migrate, rerun print tests, and run all app tests**

Run the Local Bench Sync Rule, then from `/private/tmp/vellox-frappe-bench` run:

```bash
"/Users/imac/Documents/ChatGPT/vellox erp/Elyostudio/.bench-venv/bin/bench" --site vellox.localhost migrate
"/Users/imac/Documents/ChatGPT/vellox erp/Elyostudio/.bench-venv/bin/bench" --site vellox.localhost run-tests --app vellox_agency --module vellox_agency.tests.test_offer_print_formats
"/Users/imac/Documents/ChatGPT/vellox erp/Elyostudio/.bench-venv/bin/bench" --site vellox.localhost run-tests --app vellox_agency
```

Expected: migration exits 0 and all focused and app tests PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add apps/vellox_agency/vellox_agency/templates/print_formats apps/vellox_agency/vellox_agency/vellox_agency_crm/print_format apps/vellox_agency/vellox_agency/tests/test_offer_print_formats.py
git commit -m "feat: add Vellox offer print formats"
```

---

### Task 5: Vellox Workspace Access

**Files:**
- Modify: `apps/vellox_agency/vellox_agency/vellox_agency_reports/workspace/vellox_agency/vellox_agency.json`
- Modify: `apps/vellox_agency/vellox_agency/tests/test_offer_builder_setup.py`

**Interfaces:**
- Produces: workspace shortcut `Offers` linked to `Quotation`.
- Produces: workspace master link `Services` linked to `Item`.

- [ ] **Step 1: Add a failing workspace metadata test**

Append to `TestOfferBuilderSetup`:

```python
	def test_workspace_exposes_offers_and_services(self):
		workspace = frappe.get_doc("Workspace", "Vellox Agency")
		shortcuts = {(row.label, row.link_to) for row in workspace.shortcuts}
		links = {(row.label, row.link_to) for row in workspace.links if row.link_to}
		self.assertIn(("Offers", "Quotation"), shortcuts)
		self.assertIn(("Services", "Item"), links)
```

- [ ] **Step 2: Run the setup test and confirm the intended failure**

Run the Local Bench Sync Rule, then run the Task 1 focused test command.

Expected: FAIL because the workspace has neither entry.

- [ ] **Step 3: Add the workspace entries**

Update the workspace's `content` JSON string with a shortcut block:

```json
{"id":"vel_short_offer","type":"shortcut","data":{"shortcut_name":"Offers","col":3}}
```

Add this object to `shortcuts`:

```json
{"color":"Blue","label":"Offers","link_to":"Quotation","type":"DocType"}
```

Add this object after the `Masters` card break in `links`:

```json
{"hidden":0,"is_query_report":0,"label":"Services","link_count":0,"link_to":"Item","link_type":"DocType","onboard":1,"type":"Link"}
```

- [ ] **Step 4: Migrate and run the focused and full app tests**

Run the Local Bench Sync Rule, then run the migrate command from Task 4, the Task 1 focused test, and the full app tests.

Expected: workspace test and all app tests PASS.

- [ ] **Step 5: Commit Task 5**

```bash
git add apps/vellox_agency/vellox_agency/vellox_agency_reports/workspace/vellox_agency/vellox_agency.json apps/vellox_agency/vellox_agency/tests/test_offer_builder_setup.py
git commit -m "feat: expose offers in Vellox workspace"
```

---

### Task 6: Local Bench Deployment and Acceptance

**Files:**
- Verify only; no new production files expected.

**Interfaces:**
- Consumes the completed app from Tasks 1-5.
- Produces a verified working feature on `http://vellox.localhost:8000`.

- [ ] **Step 1: Sync the source-controlled app into the active local bench copy**

The active bench contains a copy rather than a symlink. From the repository root, run:

```bash
rsync -a --exclude "__pycache__" --exclude "*.pyc" apps/vellox_agency/ /private/tmp/vellox-frappe-bench/apps/vellox_agency/
```

- [ ] **Step 2: Migrate, build, and clear cache**

The app is already synced by Step 1. From `/private/tmp/vellox-frappe-bench`, run:

```bash
"/Users/imac/Documents/ChatGPT/vellox erp/Elyostudio/.bench-venv/bin/bench" --site vellox.localhost migrate
"/Users/imac/Documents/ChatGPT/vellox erp/Elyostudio/.bench-venv/bin/bench" build --app vellox_agency
"/Users/imac/Documents/ChatGPT/vellox erp/Elyostudio/.bench-venv/bin/bench" --site vellox.localhost clear-cache
```

Expected: all three commands exit 0.

- [ ] **Step 3: Run the full automated verification suite**

From the repository root and then the active bench, run:

```bash
node --test apps/vellox_agency/vellox_agency/tests/js/test_quotation_offer_builder.js
"/private/tmp/vellox-frappe-bench/env/bin/python" -m compileall -q apps/vellox_agency/vellox_agency
git diff --check
```

```bash
"/Users/imac/Documents/ChatGPT/vellox erp/Elyostudio/.bench-venv/bin/bench" --site vellox.localhost run-tests --app vellox_agency
```

Expected: Node tests, Python compilation, whitespace checks, and all Frappe app tests PASS.

- [ ] **Step 4: Verify the EGP/USD and proposal flow in the browser**

Using the local Vellox site:

1. Open the Vellox Agency workspace and verify the `Offers` shortcut.
2. Create two non-stock Item services and populate their Vellox offer fields.
3. Add an EGP Item Price and a USD Item Price for each service using the matching selling price lists.
4. Create a Customer Quotation, select EGP, and add both services.
5. Confirm ERPNext fills the EGP rates and calculates totals.
6. Select **Build Technical Proposal** and confirm the two service sections appear in order.
7. Edit the generated proposal, change a service line, and confirm the text is preserved while the stale warning appears.
8. Rebuild, cancel once to preserve the text, then confirm once to replace it.
9. Preview `Vellox Technical Offer`, `Vellox Financial Offer`, and `Vellox Combined Offer`.
10. Repeat the financial rate check in USD.
11. Submit a Quotation and verify the build button is absent.

- [ ] **Step 5: Inspect the final diff and commit any verification-only corrections**

```bash
git status --short
git diff --check
git log -6 --oneline
```

Expected: only the user's pre-existing untracked bench and audit directories remain; tracked feature files are committed and `git diff --check` exits 0.

If browser verification required a correction, repeat its failing test, minimal fix, focused verification, full verification, and commit with:

```bash
git commit -m "fix: complete offer builder acceptance"
```
