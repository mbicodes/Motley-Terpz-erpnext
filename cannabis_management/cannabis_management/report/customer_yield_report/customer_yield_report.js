frappe.query_reports["Customer Yield Report"] = {
	filters: [
		{
			fieldname: "group_by",
			label: __("View"),
			fieldtype: "Select",
			options: ["Detail", "By Item", "By Customer", "By Sales Order"],
			default: "Detail",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -6),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
		{
			fieldname: "sales_order",
			label: __("Sales Order"),
			fieldtype: "Link",
			options: "Sales Order",
			get_query: () => {
				const customer = frappe.query_report.get_filter_value("customer");
				return { filters: customer ? { customer } : {} };
			},
		},
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group" },
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "include_drafts", label: __("Include Drafts"), fieldtype: "Check", default: 0 },
	],
};
