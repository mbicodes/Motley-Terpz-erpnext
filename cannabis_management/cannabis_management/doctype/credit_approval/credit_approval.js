frappe.ui.form.on('Credit Approval', {
	sales_order: function (frm) {
		// If a Sales Order is chosen manually, pull its customer.
		if (frm.doc.sales_order && !frm.doc.customer) {
			frappe.db.get_value('Sales Order', frm.doc.sales_order, 'customer').then(function (r) {
				if (r.message && r.message.customer) {
					frm.set_value('customer', r.message.customer);
				}
			});
		}
	}
});
