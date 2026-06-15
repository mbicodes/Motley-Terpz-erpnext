// Copyright (c) 2026, osamaASidd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Seed Selector", {
    seed(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.seed) {
            frappe.db.get_value("Item", row.seed, "item_group", (r) => {
                if (r) {
                    frappe.model.set_value(cdt, cdn, "type", r.item_group);
                }
            });
        } else {
            frappe.model.set_value(cdt, cdn, "type", "");
        }
    }
});