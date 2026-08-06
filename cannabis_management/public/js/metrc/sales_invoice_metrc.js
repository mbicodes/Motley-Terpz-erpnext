// Copyright (c) 2026, alltechvirtual.com and contributors
frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		cannabis_management.metrc.setup_form(frm);
		if (frm.doc.docstatus === 0) cannabis_management.metrc.check_rows(frm);
	},
});
