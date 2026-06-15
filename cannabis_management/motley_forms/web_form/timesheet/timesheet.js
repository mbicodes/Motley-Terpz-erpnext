frappe.ready(function() {
    frappe.call({
        method: "cannabis_management.motley_forms.api.get_current_employee",
        callback: function(r) {
            if (r.message) {
                frappe.web_form.set_value("employee", r.message.name);
                frappe.web_form.set_value("employee_name", r.message.employee_name);
                frappe.web_form.set_df_property("employee", "read_only", 1);
                frappe.web_form.set_df_property("employee_name", "read_only", 1);
            }
        }
    });
});