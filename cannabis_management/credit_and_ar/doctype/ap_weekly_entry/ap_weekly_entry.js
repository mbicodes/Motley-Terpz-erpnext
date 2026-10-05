// Copyright (c) 2026, alltechvirtual.com and contributors

frappe.ui.form.on('AP Weekly Entry', {
	refresh: function (frm) {
		if (frm.doc.supplier) {
			frm.add_custom_button(__('Supplier'), () => frappe.set_route('Form', 'Supplier', frm.doc.supplier));
			frm.add_custom_button(__('Open bills'), () => frappe.set_route('List', 'Purchase Invoice', {
				supplier: frm.doc.supplier,
				company: frm.doc.company,
				docstatus: 1,
				status: ['!=', 'Paid'],
			}));
		}
	},
});
