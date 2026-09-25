// Manufacture runs carry their own status (overrides/mr_run_status.py):
// In Progress once Work Orders are released, Completed once all of them are
// produced. Core's indicator derives the label from per_ordered and never
// reads status, so it kept showing "Pending" for these. Show them first,
// and leave every other case to core. Frappe also uses this for the form's
// status badge.
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
