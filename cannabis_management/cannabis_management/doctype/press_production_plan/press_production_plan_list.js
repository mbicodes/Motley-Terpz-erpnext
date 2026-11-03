frappe.listview_settings["Press Production Plan"] = {
    add_fields: ["status", "from_date", "to_date", "washes", "bh_planned_g"],
    // the Press Plan Board is the working screen; only System Managers see the list and form
    onload(listview) {
        if (!frappe.user.has_role("System Manager")) return frappe.set_route("press-plan-board");
        listview.page.set_primary_action(__("New Plan"), () => frappe.set_route("press-plan-board", "new"), "add");
        listview.page.add_inner_button(__("Press Plan Board"), () => frappe.set_route("press-plan-board"));
    },
    get_indicator(doc) {
        const c = { Draft: "gray", "In Progress": "orange", Completed: "green" };
        return [__(doc.status), c[doc.status] || "gray", "status,=," + doc.status];
    },
    formatters: {
        bh_planned_g: v => `${Math.round(v || 0).toLocaleString()} g`,
    },
};
