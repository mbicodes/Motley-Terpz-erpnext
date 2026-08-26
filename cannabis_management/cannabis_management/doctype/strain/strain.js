// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Strain", {
	strain_name(frm) {
		// Default the METRC strain name to the strain name until edited.
		if (frm.doc.strain_name && !frm.doc.metrc_strain_name) {
			frm.set_value("metrc_strain_name", frm.doc.strain_name);
		}
	},
});
