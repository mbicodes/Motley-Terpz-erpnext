(function () {
	const settings = (frappe.listview_settings["Material Request"] = frappe.listview_settings["Material Request"] || {});
	const core_indicator = settings.get_indicator;
	const RUN_STATUS = {
		"In Progress": "blue",
		"Completed": "green",
	};

	settings.add_fields = Array.from(new Set([...(settings.add_fields || []), "status", "material_request_type"]));
	settings.get_indicator = function (doc) {
		const color = doc.docstatus === 1 && RUN_STATUS[doc.status];
		if (color) return [__(doc.status), color, `status,=,${doc.status}`];
		return core_indicator ? core_indicator(doc) : undefined;
	};
})();
