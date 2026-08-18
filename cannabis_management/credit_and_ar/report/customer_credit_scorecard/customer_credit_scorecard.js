frappe.query_reports["Customer Credit Scorecard"] = {
	filters: [
		cannabis.reports.company_filter({ default: cannabis.reports.ALL_COMPANIES }),
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
		{
			fieldname: "customer_group",
			label: __("Customer Group"),
			fieldtype: "Link",
			options: "Customer Group",
		},
		{
			fieldname: "score_band",
			label: __("Score Band"),
			fieldtype: "Select",
			options: ["", "Excellent", "Good", "Fair", "Watch", "COD Only", "Insufficient History"],
		},
		{
			fieldname: "credit_status",
			label: __("Credit Status"),
			fieldtype: "Select",
			options: [
				"",
				"COD",
				"Terms Approved",
				"Warning",
				"Hard Hold",
				"Payment Plan",
				"Workout",
				"Blocked",
			],
		},
		{
			fieldname: "only_with_terms",
			label: __("Only Accounts With Terms"),
			fieldtype: "Check",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;

		if (column.fieldname === "score") {
			if (data.score === null || data.score === undefined || data.score === "") {
				return `<span style="color:#94a3b8">&mdash;</span>`;
			}
			const colour =
				data.score >= 750
					? "#16a34a"
					: data.score >= 700
					? "#2563eb"
					: data.score >= 650
					? "#d97706"
					: data.score >= 600
					? "#ea580c"
					: "#dc2626";
			return `<b style="color:${colour}">${data.score}</b>`;
		}

		if (column.fieldname === "past_due" && data.past_due > 0) {
			return `<span style="color:#dc2626;font-weight:600">${value}</span>`;
		}

		if (column.fieldname === "available_line" && data.available_line < 0) {
			return `<span style="color:#dc2626;font-weight:600">${value}</span>`;
		}

		if (column.fieldname === "hold_type" && data.hold_type && data.hold_type !== "None") {
			return `<span style="color:#dc2626;font-weight:600">${value}</span>`;
		}

		if (column.fieldname === "avg_days_to_pay" && data.avg_days_to_pay < 0) {
			return `<span style="color:#16a34a">${value}</span>`;
		}

		return value;
	},
};
