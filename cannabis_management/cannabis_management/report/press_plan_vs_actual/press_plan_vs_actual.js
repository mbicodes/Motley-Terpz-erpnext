frappe.query_reports["Press Plan vs Actual"] = {
    filters: [
        { fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
        { fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -30) },
        { fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), 30) },
        { fieldname: "strain", label: __("Strain"), fieldtype: "Data" },
        { fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
        { fieldname: "plan", label: __("Plan"), fieldtype: "Link", options: "Press Production Plan" },
        { fieldname: "row_status", label: __("Status"), fieldtype: "Select", options: "\nScheduled\nPressed\nWhipped\nCancelled" },
    ],
    tree: true,
    name_field: "id",
    parent_field: "parent_id",
    initial_depth: 0,
    formatter(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (column.fieldname === "variance_g" && data && data.variance_g != null) {
            value = `<span style="color:${data.variance_g < 0 ? "var(--red-600)" : "var(--green-600)"}">${value}</span>`;
        }
        return data && !data.indent ? `<b>${value}</b>` : value;
    },
};
