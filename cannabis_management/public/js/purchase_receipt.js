frappe.ui.form.on("Purchase Receipt", {
    project: function (frm) {
        if (frm.doc.project) {
            $.each(frm.doc.items || [], function (i, item) {
                frappe.model.set_value(
                    item.doctype,
                    item.name,
                    "batch",
                    frm.doc.project
                );
            });
        }
    },

    items_add: function (frm, cdt, cdn) {
        if (frm.doc.project) {
            frappe.model.set_value(cdt, cdn, "batch", frm.doc.project);
        }
    },

     validate: function(frm) {
        let has_error = false;
        
        frm.doc.items.forEach(function(row) {
            if (row.item_group === "Hardware Inventory" && !row.custom_target_customer) {
                frappe.msgprint({
                    title: __("Mandatory Field Missing"),
                    message: __(`Row ${row.idx}: Target_customer is mandatory for Hardware Inventory item <b>${row.item_code}</b>.`),
                    indicator: "red"
                });
                has_error = true;
            }
        });
        
        if (has_error) {
            frappe.validated = false;
        }
    }
});

frappe.ui.form.on("Purchase Receipt Item", {
    item_code: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        
        if (!row.item_code) return;
        
        
        frappe.db.get_value("Item", row.item_code, "item_group", function(value) {
            if (value && value.item_group === "Hardware Inventory") {
                frappe.meta.get_docfield("Purchase Receipt Item", "custom_target_customer", cdn).reqd = 1;
                frm.refresh_field("items");
                
                
                if (!row.custom_target_customer) {
                    frappe.show_alert({
                        message: __("Target_customer is mandatory for Hardware Inventory items."),
                        indicator: "orange"
                    });
                }
            } else {
               
                frappe.meta.get_docfield("Purchase Receipt Item", "custom_target_customer", cdn).reqd = 0;
                frm.refresh_field("items");
            }
        });
    }
});

