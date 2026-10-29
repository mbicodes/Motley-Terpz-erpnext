frappe.query_reports["Lab Tolling Report"] = {
	"filters": [
		{
			"fieldname": "tolling_partner",
			"label": __("Tolling Partner"),
			"fieldtype": "Link",
			"options": "Warehouse",
			"default": ""
		},
		{
			"fieldname": "batch",
			"label": __("Batch"),
			"fieldtype": "Link",
			"options": "Project",
			"default": ""
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.add_months(frappe.datetime.get_today(), -1)
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today()
		}
	]
};
