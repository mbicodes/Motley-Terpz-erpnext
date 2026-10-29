frappe.ui.form.on("Warehouse", {
    refresh: function (frm) {
        frm.set_query("custom_license", () => ({ filters: { is_company_license: 1 } }));
    },
});
