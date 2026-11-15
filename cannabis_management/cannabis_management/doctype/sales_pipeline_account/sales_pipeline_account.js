// The account form follows Sales Pipeline Settings; the board is the main place to work on accounts.
frappe.ui.form.on('Sales Pipeline Account', {
	setup(frm) {
		frm.set_query('account_owner', () => ({ query: 'cannabis_management.sales_ops.active_owner_query' }));
	},
	refresh(frm) {
		frm.add_custom_button(__('Open in Board'), () => frappe.set_route('sales-operation-board', { account: frm.is_new() ? undefined : frm.doc.name }));
		if (!frm.is_new()) {
			frm.add_custom_button(__('Deals'), () => frappe.set_route('List', 'Sales Pipeline Deal', { pipeline_account: frm.doc.name }));
		}
	},
});
