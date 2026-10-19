frappe.listview_settings["Connection Tool"] = {
	get_indicator(doc) {
		const colors = {
			Draft: "gray",
			"No Connections": "gray",
			Connected: "blue",
			"Partially Broken": "orange",
			Broken: "red",
			Relinked: "green",
		};
		return [__(doc.status), colors[doc.status] || "gray", `status,=,${doc.status}`];
	},
};
