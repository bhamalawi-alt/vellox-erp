frappe.query_reports["Vellox Project Profit"] = {
	filters: [
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nOpen\nCompleted\nCancelled",
			default: "Open",
		},
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		const colours = { Green: "green", Amber: "orange", Red: "red" };
		if (column.fieldname === "signal" && data && colours[data.signal]) {
			return `<span class="indicator-pill ${colours[data.signal]}">${value}</span>`;
		}
		return value;
	},
};
