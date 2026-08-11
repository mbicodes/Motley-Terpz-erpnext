frappe.query_reports["Terms and Credit Line Register"] = {
	filters: [
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;

		if (column.fieldname === "counsel_clause" && !data.counsel_clause) {
			return `<span style="color:#d97706" title="${__(
				"No finance charges can be assessed without this clause"
			)}">&#10007;</span>`;
		}
		if (column.fieldname === "past_due" && data.past_due > 0) {
			return `<span style="color:#dc2626;font-weight:600">${value}</span>`;
		}
		if (column.fieldname === "available_line" && data.available_line < 0) {
			return `<span style="color:#dc2626;font-weight:600">${value}</span>`;
		}
		return value;
	},
};
