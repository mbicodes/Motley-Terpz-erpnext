frappe.ui.form.on("Referral Commission Statement", {
    refresh(frm) {
        if (frm.doc.purchase_invoice) frm.add_custom_button(__("Purchase Invoice"), () => frappe.set_route("Form", "Purchase Invoice", frm.doc.purchase_invoice), __("View"));
        if (frm.doc.docstatus === 0 && !frm.is_new()) {
            frm.add_custom_button(__("Rebuild From Ledger"), () => frm.call("rebuild").then(() => frm.reload_doc()));
        }
        frm.add_custom_button(__("Ledger Lines"), () => frappe.set_route("List", "Referral Commission Ledger", { statement: frm.doc.name }), __("View"));
        if (frm.doc.docstatus === 0) frm.set_df_property("lines", "cannot_add_rows", true);
    },
});
