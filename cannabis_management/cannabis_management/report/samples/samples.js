frappe.query_reports["Samples"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "item_code",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		if (data && data.is_subtotal) {
			if (column.fieldname === "item_name") {
				return `<span style="font-weight:700;color:#1e293b;font-size:12px;letter-spacing:0.03em;">${data.item_name}</span>`;
			}
			if (column.fieldname === "amount") {
				const formatted = format_currency(data.amount, frappe.boot.sysdefaults.currency);
				return `<span style="font-weight:700;color:#b45309;font-size:12px;text-align:right;display:block;">${formatted}</span>`;
			}
			return "";
		}

		value = default_formatter(value, row, column, data);

		if (column.fieldname === "status" && data && data.status) {
			const colors = {
				"Paid":               "green",
				"Unpaid":             "red",
				"Overdue":            "orange",
				"Partly Paid":        "blue",
				"Return":             "grey",
				"Credit Note Issued": "grey",
			};
			value = `<span class="indicator-pill ${colors[data.status] || "grey"}">${data.status}</span>`;
		}

		if (column.fieldname === "amount" && data && data.amount > 0) {
			value = `<span style="font-weight:600;color:#b45309">${value}</span>`;
		}

		return value;
	},

	onload(report) {
		report.page.add_inner_button(__("View in Sales Invoice"), () => {
			const filters = report.get_values();
			frappe.set_route("List", "Sales Invoice", {
				custom_order_type: "Samples",
				docstatus: 1,
				...(filters.company  && { company:  filters.company }),
				...(filters.customer && { customer: filters.customer }),
			});
		});
	},
};