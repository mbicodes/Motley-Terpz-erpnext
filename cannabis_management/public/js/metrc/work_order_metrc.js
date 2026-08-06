// Copyright (c) 2026, alltechvirtual.com and contributors
frappe.ui.form.on("Work Order", {
	refresh(frm) {
		cannabis_management.metrc.setup_form(frm);
	},
});
