frappe.query_reports["Legacy Recovery Register"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
		{
			fieldname: "include_settled",
			label: __("Include Fully Recovered"),
			fieldtype: "Check",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;

		if (column.fieldname === "recovered_this_week" && data.recovered_this_week > 0) {
			return `<span style="color:#16a34a;font-weight:600">${value}</span>`;
		}
		if (column.fieldname === "days_past_due" && data.days_past_due > 90) {
			return `<span style="color:#dc2626;font-weight:600">${value}</span>`;
		}
		if (column.fieldname === "finance_charges") {
			return `<span style="color:#64748b">${value}</span>`;
		}
		return value;
	},
};
