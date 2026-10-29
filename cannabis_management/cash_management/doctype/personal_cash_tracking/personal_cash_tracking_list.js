frappe.listview_settings['Personal Cash Tracking'] = {
	onload: function (listview) {
		listview.page.add_inner_button(__('Cash Tracking Dashboard'), function () {
			frappe.route_options = {
				tracker: 'personal',
				from_date: moment().startOf('year').format('YYYY-MM-DD'),
				to_date: frappe.datetime.get_today()
			};
			frappe.set_route('cash-tracking-dashboard');
		});
	}
};
