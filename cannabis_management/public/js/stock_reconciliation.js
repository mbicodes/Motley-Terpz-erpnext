frappe.ui.form.on("Stock Reconciliation", {
    refresh: function (frm) {
        // Same Source/Target Tag warehouse-license filter as Stock Entry
        // (cannabis_management.metric_tag.filter_by_warehouse, loaded
        // globally via metric_tag_query.js) -- Stock Reconciliation Item has
        // only one warehouse field per row, so both tag fields are filtered
        // against it instead of separate s_warehouse/t_warehouse legs.
        cannabis_management.metric_tag.filter_by_warehouse(
            frm, "tags", "warehouse", "items",
            "cannabis_management.cannabis_management.custom.metric_tag.source_tags_for_warehouse"
        );
        cannabis_management.metric_tag.filter_by_warehouse(
            frm, "to_tags", "warehouse", "items",
            "cannabis_management.cannabis_management.custom.metric_tag.target_tags_for_warehouse"
        );
        // Reconcile Tag: an Active tag holding the row's item (Source) or an
        // Unused tag (Target). See doc_hooks/stock_reconciliation.py.
        frm.set_query("reconcile_tag", "items", function (doc, cdt, cdn) {
            const row = locals[cdt][cdn];
            return {
                query: "cannabis_management.cannabis_management.custom.metric_tag.reconcile_tags_for_warehouse",
                filters: { warehouse: row.warehouse, item_code: row.item_code },
            };
        });
    },
});

frappe.ui.form.on("Stock Reconciliation Item", {
    reconcile_tag: function (frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.reconcile_tag) {
            frappe.model.set_value(cdt, cdn, "reconcile_tag_mode", "");
            return;
        }
        frappe.db.get_value("Metric Tag", row.reconcile_tag, "status").then((r) => {
            const status = r.message && r.message.status;
            frappe.model.set_value(cdt, cdn, "reconcile_tag_mode",
                status === "Unused" ? "Target" : status === "Active" ? "Source" : "");
        });
    },
});
