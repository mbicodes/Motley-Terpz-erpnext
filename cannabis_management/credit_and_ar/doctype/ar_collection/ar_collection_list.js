frappe.listview_settings["AR Collection"] = {
	add_fields: ["stage", "written_off"],
	get_indicator(doc) {
		const colors = {
			"To Collect": "gray",
			"Reached Out": "blue",
			"Promise to Pay": "cyan",
			"Payment Plan": "purple",
			Disputed: "yellow",
			Escalated: "red",
			Collected: "green",
		};
		const label = doc.stage === "Collected" && doc.written_off ? __("Written off") : __(doc.stage);
		return [label, colors[doc.stage] || "gray", "stage,=," + doc.stage];
	},
	onload(listview) {
		listview.page.add_inner_button(__("Board View"), () => frappe.set_route("ar-collections"));
	},
};
