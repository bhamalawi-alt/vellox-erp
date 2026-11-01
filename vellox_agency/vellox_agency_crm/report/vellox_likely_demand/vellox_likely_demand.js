frappe.query_reports["Vellox Likely Demand"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "weeks", label: __("Weeks"), fieldtype: "Int", default: 8 },
	],
};
