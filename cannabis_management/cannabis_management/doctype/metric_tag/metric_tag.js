// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Metric Tag", {
	refresh(frm) {
		// Only our own facility licenses belong on a Metric Tag, never a
		// customer's/third party's.
		frm.set_query("custom_license", () => ({ filters: { is_company_license: 1 } }));
	},

	tag_code(frm) {
		if (frm.doc.tag_code) {
			frm.set_value("muid", frm.doc.tag_code.slice(-4));
		}
	},
});
