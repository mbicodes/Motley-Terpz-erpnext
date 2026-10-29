frappe.listview_settings['Conversion Entry'] = {
	onload(listview) {
		listview.page.add_inner_button(__('Dashboard'), () => {
			frappe.set_route('conversion-dashboard');
		});
	},
};
