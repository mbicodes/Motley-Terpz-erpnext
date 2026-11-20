frappe.ui.form.on("Partner Referral", {
    refresh(frm) {
        if (frm.is_new() || frm.doc.status === "Acknowledged" || frm.doc.status === "Rejected" || frm.doc.status === "Expired") return;
        frm.add_custom_button(__("Acknowledge"), () => {
            const d = new frappe.ui.Dialog({
                title: __("Acknowledge Referral"),
                fields: [
                    { fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer", default: frm.doc.customer },
                    { fieldname: "create_customer", label: __("Create a new Customer from the business name"), fieldtype: "Check", default: 0 },
                ],
                primary_action_label: __("Acknowledge"),
                primary_action: v => frm.call("acknowledge", v).then(() => { d.hide(); frm.reload_doc(); }),
            });
            d.show();
        }, __("Actions"));
        frm.add_custom_button(__("Reject"), () => {
            const d = new frappe.ui.Dialog({
                title: __("Reject Referral"),
                fields: [
                    { fieldname: "reason", label: __("Reason"), fieldtype: "Select", options: "Existing customer\nAlready in pipeline\nNot a fit\nOther", reqd: 1 },
                    { fieldname: "note", label: __("Note"), fieldtype: "Small Text", mandatory_depends_on: "eval:doc.reason=='Other'" },
                ],
                primary_action_label: __("Reject"),
                primary_action: v => frm.call("reject", v).then(() => { d.hide(); frm.reload_doc(); }),
            });
            d.show();
        }, __("Actions"));
    },
});
