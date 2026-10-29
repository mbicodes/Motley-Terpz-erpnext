frappe.query_reports["Wash Plan vs Actual"] = {
    filters: [
        { fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
        { fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -30) },
        { fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), 30) },
        { fieldname: "freezer", label: __("Freezer"), fieldtype: "Link", options: "Warehouse" },
        { fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
        { fieldname: "plan", label: __("Plan"), fieldtype: "Link", options: "Wash Production Plan" },
        { fieldname: "item", label: __("Fresh Frozen Item"), fieldtype: "Link", options: "Item" },
    ],
};
