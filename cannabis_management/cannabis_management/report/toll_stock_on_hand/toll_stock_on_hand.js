frappe.query_reports["Toll Stock On Hand"] = {
	filters: [
		{ fieldname: "as_on_date", label: __("As On Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer",
			get_query: () => ({ filters: { customer_group: "Toll Clients" } }) },
		{ fieldname: "toll_job", label: __("Toll Job"), fieldtype: "Link", options: "Toll Job" },
		{ fieldname: "warehouse", label: __("Warehouse"), fieldtype: "Link", options: "Warehouse",
			get_query: () => ({ filters: { parent_warehouse: "Toll Warehouses - MTM" } }) },
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item",
			get_query: () => ({ filters: { item_group: "Toll - Customer Owned" } }) },
	],
};
