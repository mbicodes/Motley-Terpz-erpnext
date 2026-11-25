frappe.listview_settings["Toll Job"] = {
	add_fields: ["status", "priority"],
	get_indicator(doc) {
		const colors = {
			"Received": "gray", "Queued for Wash": "blue", "Washed": "yellow", "Pressed": "orange",
			"Ready to Return": "green", "Returned": "cyan", "Invoiced": "purple", "Cancelled": "red",
		};
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
	onload(listview) {
		listview.page.add_inner_button(__("Toll Processing Board"), () => frappe.set_route("toll-processing-board"));
	},
};
