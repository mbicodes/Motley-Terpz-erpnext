frappe.query_reports["Toll Job Yield Summary"] = {
	filters: [
		{ fieldname: "from_date", label: __("Received From"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -3) },
		{ fieldname: "to_date", label: __("Received To"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer",
			get_query: () => ({ filters: { customer_group: "Toll Clients" } }) },
		{ fieldname: "group_by", label: __("Group By"), fieldtype: "Select", options: "Toll Job\nCustomer", default: "Toll Job" },
		{ fieldname: "include_cancelled", label: __("Include Cancelled Jobs"), fieldtype: "Check", default: 0 },
	],
};
