frappe.query_reports["Day Book F2"] = {
	"filters": [
		cannabis.reports.company_filter(),
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 1
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 1
		},
		{
			"fieldname": "account",
			"label": __("Account"),
			"fieldtype": "Link",
			"options": "Account",
			"get_query": function() {
				var company = frappe.query_report.get_filter_value("company");
				var filters = {
					"is_group": 0,
					"account_type": ["in", ["Cash", "Bank"]]
				};
				if (company) filters["company"] = company;
				return { filters: filters };
			}
		}
	]
};
