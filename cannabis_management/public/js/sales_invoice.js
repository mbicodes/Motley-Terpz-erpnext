// ── List View Settings ──────────────────────────────────────────────
// By default Frappe hides cancelled docs (docstatus=2) for submittable doctypes.
// We remove that restriction and add a visible, removable "Status != Cancelled"
// filter instead — so users can clear it whenever they want to see cancelled ones.
frappe.listview_settings["Sales Invoice"] = {
    onload: function (listview) {
        // 1. Remove Frappe's default docstatus=1 filter so ALL docs are fetched
        (listview.filter_area.filter_list || [])
            .filter(f => f.fieldname === "docstatus")
            .forEach(f => f.remove());

        // 2. Only add our default if no status filter is already active
        let current = listview.filter_area.get();
        let has_status = current.some(f => f[1] === "status");
        if (!has_status) {
            listview.filter_area.add([
                [listview.doctype, "status", "!=", "Cancelled"]
            ]);
        }

        listview.refresh();
    },
};

// ── Form Settings ───────────────────────────────────────────────────
frappe.ui.form.on("Sales Invoice", {
    refresh: function (frm) {
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(
                __("Material Transfer"),
                function () {
                    let d = new frappe.ui.Dialog({
                        title: __("Material Transfer"),
                        fields: [
                            {
                                fieldname: "source_warehouse",
                                fieldtype: "Link",
                                label: __("Source Warehouse"),
                                options: "Warehouse",
                                reqd: 1,
                            },
                            {
                                fieldname: "target_warehouse",
                                fieldtype: "Link",
                                label: __("Target Warehouse"),
                                options: "Warehouse",
                                reqd: 1,
                            },
                        ],
                        primary_action_label: __("Transfer"),
                        primary_action: function (values) {
                            frappe.call({
                                method: "cannabis_management.overrides.sales_invoice_utils.create_material_transfer_from_si",
                                args: {
                                    sales_invoice: frm.doc.name,
                                    source_warehouse: values.source_warehouse,
                                    target_warehouse: values.target_warehouse,
                                },
                                freeze: true,
                                freeze_message: __("Creating Material Transfer..."),
                                callback: function (r) {
                                    if (r.message) {
                                        d.hide();
                                        frappe.msgprint(r.message.message);
                                    }
                                },
                            });
                        },
                    });
                    d.show();
                },
                __("Actions")
            );
        }
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

    refresh: function (frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(
                __("Material Transfer"),
                function () {
                    show_material_transfer_dialog(frm);
                },
                __("Actions")
            );
        }
    },
});

function show_material_transfer_dialog(frm) {
    let d = new frappe.ui.Dialog({
        title: __("Material Transfer"),
        fields: [
            {
                label: __("Source Warehouse"),
                fieldname: "source_warehouse",
                fieldtype: "Link",
                options: "Warehouse",
                reqd: 1,
            },
            {
                label: __("Target Warehouse"),
                fieldname: "target_warehouse",
                fieldtype: "Link",
                options: "Warehouse",
                reqd: 1,
            },
            {
                fieldtype: "HTML",
                fieldname: "info_html",
                options:
                    '<p class="text-muted" style="margin-top:10px;">' +
                    __("Items will be transferred from the Source Warehouse to the Target Warehouse. " +
                       "If an item's requested quantity exceeds the available stock, only the available quantity will be transferred.") +
                    "</p>",
            },
        ],
        size: "small",
        primary_action_label: __("Transfer"),
        primary_action(values) {
            frappe.call({
                method:
                    "cannabis_management.overrides.sales_invoice_utils.create_material_transfer_from_si",
                args: {
                    sales_invoice: frm.doc.name,
                    source_warehouse: values.source_warehouse,
                    target_warehouse: values.target_warehouse,
                },
                freeze: true,
                freeze_message: __("Creating Material Transfer..."),
                callback: function (r) {
                    if (r.message) {
                        frappe.msgprint({
                            title: __("Material Transfer Created"),
                            message: r.message.message,
                            indicator: "green",
                        });
                        d.hide();
                        frm.reload_doc();
                    }
                },
            });
        },
    });

    d.show();
}