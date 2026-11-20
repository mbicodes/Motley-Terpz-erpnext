frappe.listview_settings['Personal Cash Tracking'] = {
	add_fields: ['transaction_type', 'workflow_state', 'docstatus'],
	has_indicator_for_draft: true,
	get_indicator: function (doc) {
		var colors = {
			'Draft': 'gray',
			'Submitted': 'blue',
			'Pending Approval': 'orange',
			'Approved': 'green',
			'Rejected': 'red',
			'Cancelled': 'red'
		};
		var state = doc.workflow_state || ['Draft', 'Submitted', 'Cancelled'][doc.docstatus];
		return [__(state), colors[state] || 'gray', 'workflow_state,=,' + state];
	},
	onload: function (listview) {
		listview.page.add_inner_button(__('Cash Tracking Dashboard'), function () {
			frappe.route_options = {
				tracker: 'personal',
				from_date: moment().startOf('year').format('YYYY-MM-DD'),
				to_date: frappe.datetime.get_today()
			};
			frappe.set_route('cash-tracking-dashboard');
		});
		listview.page.add_inner_button(__('Request Reimbursement'), function () {
			frappe.db.get_value('Cash Tracker Person',
				{ user: frappe.session.user, is_active: 1 }, 'name')
				.then(function (r) {
					var values = { transaction_type: 'Reimbursement', paid_from_safe: 1 };
					if (r.message && r.message.name) values.cash_tracker_person = r.message.name;
					frappe.new_doc('Personal Cash Tracking', values);
				});
		});
	}
};
