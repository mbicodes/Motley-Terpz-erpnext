frappe.query_reports["Sales Invoice Delivery Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			reqd: 1,
			on_change: function (report) {
				const from_date = report.get_filter_value("from_date");
				if (from_date) {
					report.set_filter_value("to_date", frappe.datetime.add_months(from_date, 1));
				}
			},
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
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
		{
			fieldname: "include_unbilled_dn",
			label: __("Include Not Invoiced Delivery Notes"),
			fieldtype: "Check",
			default: 1,
		},
	],
};
