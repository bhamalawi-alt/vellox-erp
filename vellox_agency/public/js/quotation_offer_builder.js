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

// Buttons come from the server's onload actions ([P3-98]); the server methods
// check every rule again when a button is used. A failed call has already shown
// the server's message, so callServer returns null instead of throwing.
function quotationButtons(actions) {
	if (!actions) {
		return [];
	}
	const buttons = [];
	if (actions.can_approve) {
		buttons.push("approve");
	}
	if (actions.project) {
		buttons.push("view_project");
	} else if (actions.can_create_project) {
		buttons.push("create_project");
	}
	return buttons;
}

async function callServer(options) {
	try {
		return await frappe.call(options);
	} catch (error) {
		return null;
	}
}

async function approveQuotation(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint(__("Save the quotation before approving it."));
		return;
	}
	const response = await callServer({
		method: "vellox_agency.approval.approve_quotation",
		args: { quotation: frm.doc.name },
		freeze: true,
		freeze_message: __("Approving"),
	});
	if (!response) {
		return;
	}
	frappe.show_alert({ message: __("Quotation approved"), indicator: "green" });
	await frm.reload_doc();
}

async function createProject(frm) {
	const response = await callServer({
		method: "vellox_agency.acceptance.create_project_from_quotation",
		args: { quotation: frm.doc.name },
		freeze: true,
		freeze_message: __("Creating Project"),
	});
	if (!response) {
		return;
	}
	frappe.set_route("Form", "Project", response.message.project);
}

function addQuotationActionButtons(frm) {
	const actions = (frm.doc.__onload || {}).vellox_actions;
	for (const button of quotationButtons(actions)) {
		if (button === "approve") {
			frm.add_custom_button(__("Approve Quote"), () => approveQuotation(frm)).addClass("btn-primary");
		} else if (button === "create_project") {
			frm.add_custom_button(__("Create Project"), () => createProject(frm));
		} else if (button === "view_project") {
			frm.add_custom_button(__("View Project"), () => frappe.set_route("Form", "Project", actions.project));
		}
	}
}

if (typeof module !== "undefined") {
	module.exports = { getItemSignature, isProposalStale, quotationButtons };
}

if (typeof frappe !== "undefined") {
	frappe.ui.form.on("Quotation", {
		refresh(frm) {
			updateProposalDescription(frm);
			addQuotationActionButtons(frm);
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
