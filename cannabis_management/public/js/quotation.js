// Quotation — Approve / Reject buttons for the discount-threshold approval flow.
// Buttons appear only on a draft quote that is Pending Approval, and only for a
// user eligible to approve the required tier. Server re-checks permission.

frappe.ui.form.on("Quotation", {
    onload_post_render(frm) {
        // Filter the item picker to items priced in the chosen price list.
        frm.set_query("item_code", "items", () => {
            if (frm.doc.selling_price_list) {
                return {
                    query: "cannabis_management.api.quotation_stock.items_in_price_list",
                    filters: { price_list: frm.doc.selling_price_list },
                };
            }
            return {};
        });
    },

    refresh(frm) {
        // ── Live stock: "Check Stock Availability" dialog ──
        if (!frm.is_new() && (frm.doc.items || []).length) {
            frm.add_custom_button(__("Check Stock Availability"), () => showStockDialog(frm));
        }

        // ── Approved + submitted → offer one-click Sales Order conversion ──
        if (frm.doc.docstatus === 1 && frm.doc.custom_approval_status === "Approved") {
            frm.add_custom_button(__("Create Sales Order"), () => {
                frappe.call({
                    method:
                        "cannabis_management.overrides.quote_to_order.create_sales_order_from_quotation",
                    args: { quotation: frm.doc.name },
                    freeze: true,
                    freeze_message: __("Creating Sales Order..."),
                    callback: (r) => {
                        if (r.message && r.message.sales_order) {
                            frappe.set_route("Form", "Sales Order", r.message.sales_order);
                        }
                    },
                });
            }).addClass("btn-primary");
        }

        if (frm.is_new() || frm.doc.docstatus !== 0) return;
        if (frm.doc.custom_approval_status !== "Pending Approval") return;

        const level = frm.doc.custom_required_approval_level;
        const roles = frappe.user_roles || [];
        const isSuper =
            frappe.session.user === "Administrator" || roles.includes("Super Admin");
        const isFinance =
            isSuper || roles.includes("Finance Manager") || roles.includes("Accounts Manager");
        const isManager = isFinance || roles.includes("Sales Manager");

        const canApprove =
            level === "Finance" ? isFinance : level === "Sales Manager" ? isManager : false;
        if (!canApprove) return;

        frm.add_custom_button(__("Approve Quotation"), () => {
            frappe.confirm(
                __("Approve this quotation (effective discount {0}%)?", [
                    frm.doc.custom_discount_pct_effective || 0,
                ]),
                () => {
                    frappe.call({
                        method:
                            "cannabis_management.overrides.quotation_approval.approve_quotation",
                        args: { name: frm.doc.name },
                        freeze: true,
                        freeze_message: __("Approving..."),
                        callback: () => {
                            frappe.show_alert({ message: __("Quotation approved"), indicator: "green" });
                            frm.reload_doc();
                        },
                    });
                }
            );
        }).addClass("btn-primary");

        frm.add_custom_button(__("Reject Quotation"), () => {
            frappe.prompt(
                [
                    {
                        fieldname: "reason",
                        fieldtype: "Small Text",
                        label: __("Rejection Reason"),
                        reqd: 1,
                    },
                ],
                (values) => {
                    frappe.call({
                        method:
                            "cannabis_management.overrides.quotation_approval.reject_quotation",
                        args: { name: frm.doc.name, reason: values.reason },
                        freeze: true,
                        freeze_message: __("Rejecting..."),
                        callback: () => {
                            frappe.show_alert({ message: __("Quotation rejected"), indicator: "orange" });
                            frm.reload_doc();
                        },
                    });
                },
                __("Reject Quotation"),
                __("Reject")
            );
        });
    },
});

// ── Live Bin stock per line ──────────────────────────────────────────────────
frappe.ui.form.on("Quotation Item", {
    item_code(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.item_code) return;
        frappe.call({
            method: "cannabis_management.api.quotation_stock.get_item_availability",
            args: { item_codes: JSON.stringify([row.item_code]) },
            callback: (r) => {
                const info = (r.message || {})[row.item_code];
                frappe.model.set_value(cdt, cdn, "custom_available_stock", info ? info.available : 0);
            },
        });
    },
});

function showStockDialog(frm) {
    const codes = [...new Set((frm.doc.items || []).map((i) => i.item_code).filter(Boolean))];
    if (!codes.length) {
        frappe.msgprint(__("Add items first."));
        return;
    }
    frappe.call({
        method: "cannabis_management.api.quotation_stock.get_item_availability",
        args: { item_codes: JSON.stringify(codes) },
        freeze: true,
        callback: (r) => {
            const data = r.message || {};
            let html = `<table class="table table-bordered" style="font-size:12px;">
                <thead><tr><th>Item</th><th style="text-align:right">Available</th><th>Warehouses</th></tr></thead><tbody>`;
            codes.forEach((code) => {
                const info = data[code] || { available: 0, warehouses: [] };
                const wh = (info.warehouses || [])
                    .map((w) => `${frappe.utils.escape_html(w.warehouse)}: ${format_number(w.available)}`)
                    .join("<br>") || "<span style='color:#94a3b8'>no stock</span>";
                const color = info.available > 0 ? "#059669" : "#dc2626";
                html += `<tr>
                    <td>${frappe.utils.escape_html(code)}</td>
                    <td style="text-align:right;font-weight:700;color:${color}">${format_number(info.available)}</td>
                    <td>${wh}</td></tr>`;
            });
            html += "</tbody></table>";
            frappe.msgprint({ title: __("Live Stock Availability"), message: html, wide: true });
        },
    });
}
