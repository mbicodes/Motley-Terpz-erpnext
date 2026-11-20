frappe.ui.form.on("Referral Partner", {
    refresh(frm) {
        if (frm.is_new()) return;
        if (frm.doc.status !== "Active") {
            frm.add_custom_button(__("Activate"), () => {
                frappe.confirm(__("Create the portal user and Supplier, send the set-password email and activate this partner?"), () =>
                    frm.call("activate").then(() => frm.reload_doc()));
            }).addClass("btn-primary");
        }
        if (frm.doc.status === "Active") {
            frm.add_custom_button(__("Terminate"), () => {
                frappe.prompt({ fieldname: "termination_date", label: __("Termination Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
                    v => frm.call("terminate", { termination_date: v.termination_date }).then(() => frm.reload_doc()),
                    __("Terminate Partner"), __("Terminate"));
            });
        }
        if (frm.doc.status !== "Draft") {
            frm.add_custom_button(__("Referral Program Board"), () => frappe.set_route("referral-program-board"));
        }
    },
});
