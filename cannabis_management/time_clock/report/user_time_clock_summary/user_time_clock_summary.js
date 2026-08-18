frappe.query_reports["User Time Clock Summary"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "user",
			label: __("User"),
			fieldtype: "Link",
			options: "User",
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		// Flag sessions that were never clocked out so missing punches stand out.
		if (column.fieldname === "status" && data && data.status !== "Complete") {
			value = `<span style="color:#b45309;font-weight:600">${value}</span>`;
		}
		return value;
	},
};
