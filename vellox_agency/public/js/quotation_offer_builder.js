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
