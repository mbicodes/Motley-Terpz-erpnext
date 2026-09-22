// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.query_reports["Sales Document Links"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -3),
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
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			// Trace one document end to end: pick it here and the report shows
			// only the chain it belongs to.
			fieldname: "sales_order",
			label: __("Sales Order"),
			fieldtype: "Link",
			options: "Sales Order",
		},
		{
			fieldname: "delivery_note",
			label: __("Delivery Note"),
			fieldtype: "Link",
			options: "Delivery Note",
		},
		{
			fieldname: "sales_invoice",
			label: __("Sales Invoice"),
			fieldtype: "Link",
			options: "Sales Invoice",
		},
		{
			// The gaps are usually the point of running this.
			fieldname: "link_status",
			label: __("Link Status"),
			fieldtype: "Select",
			options: [
				"",
				"Complete",
				"Invoice not delivered",
				"Delivery not invoiced",
				"No Sales Order",
			].join("\n"),
		},
		{
			fieldname: "include_draft",
			label: __("Include Drafts"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "include_cancelled",
			label: __("Include Cancelled"),
			fieldtype: "Check",
			default: 0,
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "link_status" && data) {
			const colour = {
				"Complete": "green",
				"Invoice not delivered": "orange",
				"Delivery not invoiced": "orange",
				"No Sales Order": "red",
			}[data.link_status];
			if (colour) value = `<span style="color:var(--text-on-light-${colour}, ${colour})">${value}</span>`;
		}
		return value;
	},
};
