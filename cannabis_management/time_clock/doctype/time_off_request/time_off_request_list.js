frappe.listview_settings["Time Off Request"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const c = { Pending: "orange", Approved: "green", Taken: "blue", Denied: "red", Cancelled: "gray", "Not Taken": "gray" };
		return [__(doc.status), c[doc.status] || "gray", "status,=," + doc.status];
	},
};
