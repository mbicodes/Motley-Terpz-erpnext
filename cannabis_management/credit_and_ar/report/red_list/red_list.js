frappe.query_reports["Red List"] = {
	filters: [
		cannabis.reports.company_filter({ default: cannabis.reports.ALL_COMPANIES }),
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "HOLD", "PLAN", "WORKOUT", "PAST DUE"],
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;

		if (column.fieldname === "status") {
			const colours = {
				HOLD: "#dc2626",
				PLAN: "#2563eb",
				WORKOUT: "#7c3aed",
				"PAST DUE": "#ea580c",
			};
			return `<b style="color:${colours[data.status] || "#334155"}">${data.status}</b>`;
		}
		if (column.fieldname === "past_due" && data.past_due > 0) {
			return `<span style="color:#dc2626;font-weight:600">${value}</span>`;
		}
		if (column.fieldname === "max_days" && data.max_days > 30) {
			return `<span style="color:#dc2626;font-weight:600">${value}</span>`;
		}
		if (column.fieldname === "missed_installments" && data.missed_installments > 0) {
			return `<span style="color:#dc2626;font-weight:600">${value}</span>`;
		}
		if (
			column.fieldname === "promise_to_pay_date" &&
			data.promise_to_pay_date &&
			frappe.datetime.get_day_diff(data.promise_to_pay_date, frappe.datetime.get_today()) < 0
		) {
			return `<span style="color:#dc2626;font-weight:600">${value}</span>`;
		}
		return value;
	},
};
