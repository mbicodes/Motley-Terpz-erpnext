// Form rules follow Sales Pipeline Settings (stages, owners); the server enforces the same rules on save.
frappe.ui.form.on('Sales Pipeline Deal', {
	setup(frm) {
		frm.set_query('deal_owner', () => ({ query: 'cannabis_management.sales_ops.active_owner_query' }));
	},
	onload(frm) {
		frappe.xcall('cannabis_management.cannabis_management.page.sales_operation_board.sales_operation_board.get_form_settings')
			.then(s => { frm.spb_settings = s; frm.trigger('apply_stage_rules'); });
	},
	refresh(frm) {
		frm.trigger('apply_stage_rules');
		frm.add_custom_button(__('Open in Board'), () => frappe.set_route('sales-operation-board', { deal: frm.is_new() ? undefined : frm.doc.name }));
		if (!frm.is_new() && frappe.model.can_create('Quotation')) {
			frm.add_custom_button(__('Quotation'), () => {
				frappe.xcall('cannabis_management.cannabis_management.page.sales_operation_board.sales_operation_board.make_quotation', { name: frm.doc.name })
					.then(r => {
						if (r.message) frappe.show_alert({ message: r.message, indicator: 'orange' });
						frappe.model.sync(r.doc);
						frappe.set_route('Form', r.doc.doctype, r.doc.name);
					});
			}, __('Create'));
		}
	},
	stage(frm) {
		frm.trigger('apply_stage_rules');
	},
	apply_stage_rules(frm) {
		const s = frm.spb_settings;
		if (!s) return;
		const st = (s.stages || []).find(x => x.name === frm.doc.stage) || {};
		const lost = !!(st.is_closed && !st.is_won);
		frm.toggle_reqd('next_step_due', !!st.name && !st.is_closed && st.name !== s.first_stage);
		frm.toggle_reqd('customer', !!(st.is_closed && st.is_won));
		frm.toggle_display('lost_reason', lost || !!frm.doc.lost_reason);
		frm.toggle_reqd('lost_reason', lost);
	},
});
