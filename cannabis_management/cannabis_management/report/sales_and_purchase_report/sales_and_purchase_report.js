// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.query_reports["Sales and Purchase Report"] = {
	"filters": [
		{
			"fieldname": "type",
			"label": __("Type"),
			"fieldtype": "Select",
			"options": "Sales\nPurchase\nCost Reconciliation",
			"default": "Sales",
			"reqd": 1,
			"on_change": function () {
				var type = frappe.query_report.get_filter_value("type");
				var party_filter = frappe.query_report.get_filter("party");
				if (!party_filter) return;
				if (type === "Cost Reconciliation") {
					party_filter.df.hidden = 1;
					party_filter.set_value("");
				} else {
					var doctype = type === "Purchase" ? "Supplier" : "Customer";
					party_filter.df.hidden = 0;
					party_filter.df.options = doctype;
					party_filter.df.label = __(doctype);
					party_filter.set_value("");
				}
				party_filter.refresh();
			},
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
		},
		{
			"fieldname": "party",
			"label": __("Customer"),
			"fieldtype": "Link",
			"options": "Customer",
		},
		{
			"fieldname": "company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"default": frappe.defaults.get_user_default("Company"),
		},
	],
};
