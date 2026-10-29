frappe.ui.form.on('Farm Daily Report', {
	setup(frm) {
		frm.set_query('flc', 'flc_labor', () => ({
			filters: { supplier_group: 'FLC', disabled: 0 }
		}));
		frm.set_query('activity', 'activities', () => ({
			filters: { disabled: 0 }
		}));
	}
});
