frappe.ui.form.on("Warehouse", {
    refresh: function (frm) {
        // Only our own facility licenses belong on a Warehouse, never a
        // customer's/third party's.
        frm.set_query("custom_license", () => ({ filters: { is_company_license: 1 } }));
    },
});
