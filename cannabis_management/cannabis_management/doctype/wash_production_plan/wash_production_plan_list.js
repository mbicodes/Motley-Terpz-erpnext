frappe.listview_settings["Wash Production Plan"] = {
    add_fields: ["status", "from_date", "to_date", "total_washes", "total_planned_lbs"],
    // the Wash Plan Board is the working screen; only System Managers see the list and form
    onload(listview) {
        if (!frappe.user.has_role("System Manager")) return frappe.set_route("wash-plan-board");
        listview.page.set_primary_action(__("New Plan"), () => frappe.set_route("wash-plan-board", "new"), "add");
        listview.page.add_inner_button(__("Wash Plan Board"), () => frappe.set_route("wash-plan-board"));
    },
    get_indicator(doc) {
        const c = { Draft: "gray", "In Progress": "orange", Completed: "green", Cancelled: "red" };
        return [__(doc.status), c[doc.status] || "gray", "status,=," + doc.status];
    },
    formatters: {
        total_planned_lbs: v => `${Math.round(v || 0)} lbs`,
    },
};
