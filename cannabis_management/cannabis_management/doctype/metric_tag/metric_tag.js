// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Metric Tag", {
	tag_code(frm) {
		if (frm.doc.tag_code) {
			frm.set_value("muid", frm.doc.tag_code.slice(-4));
		}
	},
});
