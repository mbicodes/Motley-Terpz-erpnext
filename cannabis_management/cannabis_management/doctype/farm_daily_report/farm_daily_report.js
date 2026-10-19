// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.ui.form.on('Farm Daily Report', {
	setup(frm) {
		// Same list the web page shows: active suppliers in the FLC group.
		frm.set_query('flc', 'flc_labor', () => ({
			filters: { supplier_group: 'FLC', disabled: 0 }
		}));
		frm.set_query('activity', 'activities', () => ({
			filters: { disabled: 0 }
		}));
	}
});
