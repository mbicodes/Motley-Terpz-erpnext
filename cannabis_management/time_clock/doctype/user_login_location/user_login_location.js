frappe.ui.form.on("User Login Location", {
	refresh(frm) {
		if (frm.doc.latitude && frm.doc.longitude) {
			frm.add_custom_button(__("Open in Google Maps"), () => {
				window.open(
					`https://www.google.com/maps?q=${frm.doc.latitude},${frm.doc.longitude}`,
					"_blank"
				);
			});
		}
	},
});
