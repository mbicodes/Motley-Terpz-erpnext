// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Production Batch Group", {
    ff_weight_received_lbs(frm) {
        const lbs = frm.doc.ff_weight_received_lbs || 0;
        frm.set_value("ff_weight_received_g", Math.round(lbs * 453.592 * 100) / 100);
    },

    refresh(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__("Refresh Yields"), function () {
                frappe.call({
                    method: "frappe.client.save",
                    args: { doc: frm.doc },
                    callback: () => frm.reload_doc()
                });
            }, __("Actions"));

            frm.add_custom_button(__("Create Wash Batch"), function () {
                frappe.new_doc("Wash Batch", {
                    production_batch_group: frm.doc.name,
                    strain_name: frm.doc.strain_name
                });
            }, __("Actions"));

            frm.add_custom_button(__("Create Press Batch"), function () {
                frappe.new_doc("Press Batch", {
                    production_batch_group: frm.doc.name,
                    strain_name: frm.doc.strain_name
                });
            }, __("Actions"));
        }
    }
});
