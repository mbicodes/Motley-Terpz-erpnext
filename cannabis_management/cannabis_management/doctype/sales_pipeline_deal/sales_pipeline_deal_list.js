frappe.listview_settings['Sales Pipeline Deal'] = {
	add_fields: ['stage', 'deal_owner'],
	onload(listview) {
		listview.page.add_inner_button(__('Sales Operation Board'), () => frappe.set_route('sales-operation-board'));
		frappe.xcall('cannabis_management.cannabis_management.page.sales_operation_board.sales_operation_board.get_form_settings')
			.then(s => { frappe.listview_settings['Sales Pipeline Deal'].stages = s.stages || []; listview.refresh(); });
	},
	get_indicator(doc) {
		const stages = frappe.listview_settings['Sales Pipeline Deal'].stages || [];
		const st = stages.find(x => x.name === doc.stage) || {};
		const color = st.is_closed ? (st.is_won ? 'green' : 'gray') : 'blue';
		return [__(doc.stage), color, 'stage,=,' + doc.stage];
	},
};
