// Copyright (c) 2026, alltechvirtual.com and contributors
frappe.ui.form.on("Stock Reconciliation", {
	refresh(frm) {
		cannabis_management.metrc.setup_form(frm);
	},
});
