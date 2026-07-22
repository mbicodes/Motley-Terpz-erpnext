frappe.listview_settings['Motley Cash Tracking'] = {
	onload: function (listview) {
		// Open the Cash Tracking dashboard with the Motley tracker preselected
		// and the date range set to the start of the current year through today.
		listview.page.add_inner_button(__('Cash Tracking Dashboard'), function () {
			frappe.route_options = {
				tracker: 'motley',
				from_date: moment().startOf('year').format('YYYY-MM-DD'),
				to_date: frappe.datetime.get_today()
			};
			frappe.set_route('cash-tracking-dashboard');
		});
	}
};
