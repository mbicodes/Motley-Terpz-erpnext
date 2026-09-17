frappe.ui.form.on("Delivery Note", {
    refresh: function (frm) {
        // Source/Target Tags: only offer Metric Tags whose License matches
        // the row's Warehouse/Target Warehouse.
        cannabis_management.metric_tag.filter_by_warehouse(frm, "tags", "warehouse");
        cannabis_management.metric_tag.filter_by_warehouse(frm, "to_tags", "target_warehouse");
    },

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
});