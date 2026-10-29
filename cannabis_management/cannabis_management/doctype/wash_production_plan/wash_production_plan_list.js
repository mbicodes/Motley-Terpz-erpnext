frappe.listview_settings["Wash Production Plan"] = {
    add_fields: ["status", "from_date", "to_date", "total_washes", "total_planned_lbs"],
    get_indicator(doc) {
        const c = { Draft: "gray", "In Progress": "orange", Completed: "green", Cancelled: "red" };
        return [__(doc.status), c[doc.status] || "gray", "status,=," + doc.status];
    },
    formatters: {
        total_planned_lbs: v => `${Math.round(v || 0)} lbs`,
    },
};
