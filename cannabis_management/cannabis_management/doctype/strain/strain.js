frappe.ui.form.on("Strain", {
	strain_name(frm) {
		if (frm.doc.strain_name && !frm.doc.metrc_strain_name) {
			frm.set_value("metrc_strain_name", frm.doc.strain_name);
		}
	},
});
