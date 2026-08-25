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
