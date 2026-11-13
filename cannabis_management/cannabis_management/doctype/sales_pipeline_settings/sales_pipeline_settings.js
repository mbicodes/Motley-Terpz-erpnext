frappe.ui.form.on('Sales Pipeline Settings', {
	refresh(frm) {
		frm.add_custom_button(__('Sales Operation Board'), () => frappe.set_route('sales-operation-board'));
	},
});
