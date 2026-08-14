# Vellox Technical and Financial Offer Builder Design

## Purpose

Vellox staff need to prepare a client-ready technical and financial offer by selecting a client and one or more services. Each service stores reusable technical proposal text and commercial defaults. The offer must remain easy to edit and must use ERPNext's standard selling records rather than create a parallel quotation or client system.

## Design Decisions

- ERPNext `Customer`, `Contact`, and `Address` remain authoritative for client information.
- ERPNext `Item` remains authoritative for each sellable Vellox service.
- ERPNext `Item Price` remains authoritative for default EGP and USD prices.
- ERPNext `Quotation` remains authoritative for the financial offer, currency, taxes, discounts, validity, terms, totals, workflow status, and downstream sales documents.
- Vellox adds a small set of custom fields and proposal-generation behavior to `Item` and `Quotation`.
- No new Offer, Client, Service, or Financial Offer DocType will be introduced in this phase.
- One quotation can be printed as a technical offer, a financial offer, or a combined technical and financial offer.

## Service Setup

A Vellox service is a standard non-stock ERPNext Item. The standard Item record supplies the service name, item code, sales description, unit of measure, tax configuration, and prices. Vellox adds only these fields:

| Field | Type | Purpose |
| --- | --- | --- |
| Technical Proposal Template | Text Editor | Reusable formatted proposal text for this service. It may contain scope, approach, deliverables, assumptions, exclusions, and other service-specific language in one editable document. |
| Default Duration | Data | A compact human-readable duration such as `6 weeks` or `3 months`. |
| Billing Method | Select | One of `Fixed Price`, `Milestone`, `Retainer`, or `Time and Materials`. |
| Project Template | Link to Project Template | Optional project programme to use after the client accepts the offer. |

The default price is not duplicated in a custom field. It comes from ERPNext Item Price records for the selected EGP or USD price list.

## Offer Screen

Vellox uses the existing ERPNext Quotation form. The normal fields already provide:

- Client or lead
- Client contact and address
- Offer title and date
- Currency and price list
- Validity date
- Selected services
- Quantities and rates
- Discounts and taxes
- Payment and commercial terms
- Financial totals
- Draft, submitted, ordered, lost, and expired states

Vellox adds one visible field to the Quotation:

| Field | Type | Purpose |
| --- | --- | --- |
| Technical Proposal | Text Editor | The generated, offer-specific technical proposal. Staff can edit it without changing the service templates. |

Any internal item-signature field required to detect changes is hidden and read-only. It must not clutter the form.

## User Flow

1. The user creates a Quotation and selects a Customer or Lead.
2. The user selects EGP or USD and the corresponding price list.
3. The user adds one or more service Items. ERPNext supplies the financial lines and default prices.
4. The user selects **Build Technical Proposal**.
5. Vellox reads the selected services in quotation-line order and generates one proposal section per service.
6. Each generated section contains the service name, technical proposal template, default duration when present, and billing method when present.
7. The user edits the generated Technical Proposal for the specific client.
8. The user adjusts quantities, prices, discounts, taxes, validity, and terms using standard Quotation behavior.
9. The user previews or prints the technical, financial, or combined offer.
10. The user submits the Quotation through the standard ERPNext process.

The generator never silently replaces edited proposal text. If the quotation's service selection changes after generation, the form shows that the proposal is out of date. Running **Build Technical Proposal** again requires confirmation and then replaces the current proposal with a fresh composition from the selected service templates.

## Proposal Composition Rules

- Only unique service Items with non-empty Technical Proposal Templates produce technical sections.
- Repeated quotation lines for the same service produce one technical section, while all financial lines remain unchanged.
- Sections follow the first appearance of each service in the quotation.
- The service name is rendered as a heading.
- Default Duration and Billing Method are rendered as compact metadata below the heading only when populated.
- Stored rich text is preserved and passed through Frappe's normal sanitization path.
- Services without proposal text remain valid financial lines and are reported to the user as skipped; they do not block quotation creation.
- Building a proposal with no eligible service text returns a clear message and leaves the current Technical Proposal unchanged.

## Outputs

Three branded print formats are provided:

1. **Vellox Technical Offer** — client details, title, date, validity, and Technical Proposal.
2. **Vellox Financial Offer** — client details, service lines, currency, prices, discounts, taxes, totals, and commercial terms.
3. **Vellox Combined Offer** — technical content followed by the complete financial offer.

The first release uses English labels and preserves Arabic rich text entered in service templates or the offer. A dedicated bilingual layout and automatic translation are outside this phase.

## Permissions and Audit

- Existing ERPNext Quotation permissions remain authoritative.
- Users must be able to read Item records to generate proposal sections.
- Only users permitted to edit a draft Quotation can replace its Technical Proposal.
- Submitted and cancelled quotations cannot regenerate proposal text.
- Price editing, discount limits, submission, and approval remain governed by ERPNext roles and future Vellox workflows.
- Quotation versioning and comments provide the offer audit trail; no second revision store is introduced.

## Error Handling

- Missing or disabled Items are rejected by standard Quotation validation.
- Missing service proposal templates are reported as skipped service names.
- Server errors do not clear or partially replace existing proposal text.
- The client displays generation errors through standard Frappe messages.
- The generator is deterministic: the same ordered services and templates produce the same proposal.

## Installation and Upgrade Behavior

- Custom fields, client script registration, and print formats are owned by the `vellox_agency` app and stored in source control.
- Setup is idempotent so a fresh install and a later migration produce the same metadata.
- ERPNext source files are not modified.
- The feature targets the ERPNext and Frappe versions already installed on the Vellox bench.

## Testing and Acceptance Criteria

Automated tests must prove that:

1. Two configured service Items generate two ordered technical sections.
2. Duplicate service lines generate only one technical section.
3. Duration and billing method appear only when set.
4. A service without proposal text is skipped and reported without blocking other services.
5. No eligible service leaves the current proposal unchanged and returns a clear error.
6. Regeneration is rejected for submitted or cancelled quotations.
7. Users without the required permissions cannot invoke the update path.
8. EGP and USD quotations continue to use standard Item Price and Quotation calculations.
9. The three print formats render the correct technical and financial sections.
10. Migration creates the required metadata without modifying ERPNext files.

The local acceptance scenario is:

- Create one Customer and two non-stock service Items.
- Give both services proposal templates and EGP/USD Item Prices.
- Create a draft Quotation for the Customer in each currency.
- Select the services and generate the Technical Proposal.
- Edit the generated text and verify that changing an item does not overwrite it silently.
- Regenerate after confirmation.
- Preview all three print formats.
- Submit the Quotation and verify regeneration is unavailable.

## Out of Scope

- Automatic proposal writing or translation with AI
- Electronic signatures and a client portal
- New approval workflows or discount thresholds
- Automatic contract creation
- Automatic Project creation from the linked Project Template
- Milestone schedule generation
- Social media functionality

These capabilities may be added in later, separately approved ERP phases. This phase ends with a reliable, compact technical and financial offer builder on standard ERPNext Item and Quotation records.
