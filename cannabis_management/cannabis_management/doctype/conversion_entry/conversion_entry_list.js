frappe.listview_settings['Conversion Entry'] = {
	onload(listview) {
		// Straight to the Conversion & Tolling dashboard (page/conversion_dashboard).
		listview.page.add_inner_button(__('Dashboard'), () => {
			frappe.set_route('conversion-dashboard');
		});
	},
};
