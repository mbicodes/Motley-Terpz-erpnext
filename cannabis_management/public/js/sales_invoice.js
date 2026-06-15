// ── List View Settings ──────────────────────────────────────────────
// Remove Frappe's default docstatus=1 filter and add a visible,
// removable "Status != Cancelled" filter instead.
frappe.listview_settings["Sales Invoice"] = {
    onload: function (listview) {
        (listview.filter_area.filter_list || [])
            .filter(f => f.fieldname === "docstatus")
            .forEach(f => f.remove());

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

// ── Form ────────────────────────────────────────────────────────────
frappe.ui.form.on("Sales Invoice", {

    refresh: function (frm) {
        // Material Transfer action — only on saved/submitted docs
        if (!frm.is_new()) {
            frm.add_custom_button(
                __("Material Transfer"),
                function () { show_material_transfer_dialog(frm); },
                __("Actions")
            );
        }

        // AR Policy: hide Print if customer outstanding > $20k (non-admin only)
        _check_print_access(frm);
    },

    customer: function (frm) {
        // Re-evaluate print access whenever the customer field changes
        _check_print_access(frm);
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


// ── AR Policy: print access check ───────────────────────────────────

function _check_print_access(frm) {
    if (!frm.doc.customer) return;

    // Admins always have print access — skip the check entirely
    if (
        frappe.user.has_role("System Manager") ||
        frappe.user.has_role("Administrator") ||
        frappe.session.user === "Administrator"
    ) {
        return;
    }

    frappe.call({
        method: "cannabis_management.api.ar_dashboard.get_customer_gl_balance",
        args: { customer: frm.doc.customer },
        callback: function (r) {
            const balance = r.message || 0;
            if (balance > 20000) {
                _hide_print_btn(frm);
                frappe.show_alert({
                    message: __(
                        "Print disabled — {0} has an outstanding balance of ${1}. " +
                        "Contact Finance or an Admin to print.",
                        [
                            frm.doc.customer,
                            parseFloat(balance).toLocaleString("en-US", {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                            }),
                        ]
                    ),
                    indicator: "orange",
                }, 7);
            }
        },
    });
}

function _hide_print_btn(frm) {
    // frm.toolbar.print_btn is the standard Frappe toolbar print button
    if (frm.toolbar && frm.toolbar.print_btn) {
        frm.toolbar.print_btn.hide();
        return;
    }
    // Fallback: find the print button in the page actions area
    frm.page.wrapper
        .find('.page-actions button, .page-head button')
        .filter(function () {
            const lbl = ($(this).attr("data-label") || $(this).text()).toLowerCase();
            return lbl.includes("print");
        })
        .hide();
}


// ── Material Transfer dialog ─────────────────────────────────────────

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
                    __(
                        "Items will be transferred from the Source Warehouse to the " +
                        "Target Warehouse. If an item's requested quantity exceeds " +
                        "available stock, only the available quantity will be transferred."
                    ) +
                    "</p>",
            },
        ],
        size: "small",
        primary_action_label: __("Transfer"),
        primary_action(values) {
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
