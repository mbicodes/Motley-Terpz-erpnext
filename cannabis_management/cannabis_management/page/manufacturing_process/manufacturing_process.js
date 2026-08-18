/* Desk shell for the Manufacturing Process page.
 *
 * All behaviour lives in public/js/manufacturing_process_app.js, which the portal
 * page at /manufacturing-process mounts as well. Keep this file free of business
 * logic — the whole point of the split is that the two shells cannot drift.
 *
 * The shared module is loaded in Desk via `app_include_js` in hooks.py.
 */
frappe.pages['manufacturing-process'].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Manufacturing Process',
		single_column: true,
	});

	// Supports /app/manufacturing-process/WO-0001 — resolving the route is a
	// shell concern, so it happens here rather than in the shared module.
	var route = frappe.get_route();

	cannabis.manufacturingProcess.mount($(wrapper).find('.layout-main-section')[0], {
		initialWorkOrder: route && route.length > 1 ? route[1] : null,
	});
};
