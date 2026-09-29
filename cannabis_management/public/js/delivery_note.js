frappe.ui.form.on("Delivery Note", {
    refresh: function (frm) {
        // Source/Target Tags: only offer Metric Tags whose License matches
        // the row's Warehouse/Target Warehouse.
        cannabis_management.metric_tag.filter_by_warehouse(frm, "tags", "warehouse");
        cannabis_management.metric_tag.filter_by_warehouse(frm, "to_tags", "target_warehouse");

        // View > Accounting Ledger: core opens it from posting_date to the
        // note's *modified* date, which is often a different day (and can
        // even land before posting_date). Pin both ends to the posting date.
        // This handler runs before the controller's refresh, which is what
        // calls show_general_ledger(), so shadowing the method here is enough.
        frm.cscript.show_general_ledger = function () {
            if (frm.doc.docstatus > 0) {
                frm.add_custom_button(__("Accounting Ledger"), function () {
                    frappe.route_options = {
                        voucher_no: frm.doc.name,
                        from_date: frm.doc.posting_date,
                        to_date: frm.doc.posting_date,
                        company: frm.doc.company,
                        categorize_by: "Categorize by Voucher (Consolidated)",
                        show_cancelled_entries: frm.doc.docstatus === 2,
                        ignore_prepared_report: true,
                    };
                    frappe.set_route("query-report", "General Ledger");
                }, __("View"));
            }
        };
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