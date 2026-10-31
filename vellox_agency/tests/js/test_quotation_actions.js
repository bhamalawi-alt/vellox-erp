const test = require("node:test");
const assert = require("node:assert/strict");
const { quotationButtons } = require("../../public/js/quotation_offer_builder.js");

test("no buttons without server actions", () => {
	assert.deepEqual(quotationButtons(undefined), []);
	assert.deepEqual(quotationButtons({}), []);
});

test("buttons follow the server's actions", () => {
	assert.deepEqual(quotationButtons({ can_approve: true }), ["approve"]);
	assert.deepEqual(quotationButtons({ can_create_project: true }), ["create_project"]);
	assert.deepEqual(quotationButtons({ project: "PROJ-0001" }), ["view_project"]);
	assert.deepEqual(quotationButtons({ can_create_project: true, project: "PROJ-0001" }), ["view_project"]);
});
