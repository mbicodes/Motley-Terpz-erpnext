frappe.ui.form.on("Press Production Plan", {
    onload(frm) {
        // the Board is the only screen for non-admins; the form stays as storage and for System Managers
        if (!frappe.user.has_role("System Manager")) frappe.set_route("press-plan-board", frm.is_new() ? "new" : frm.doc.name);
    },
    refresh(frm) {
        frm.trigger("plan_type");
        if (!frm.is_new()) frm.add_custom_button(__("Press Plan Board"), () => frappe.set_route("press-plan-board", frm.doc.name));
    },
    plan_type(frm) {
        frm.set_df_property("to_date", "read_only", frm.doc.plan_type !== "Custom");
    },
});
