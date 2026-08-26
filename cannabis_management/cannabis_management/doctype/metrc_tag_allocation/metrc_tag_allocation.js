// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("METRC Tag Allocation", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.status !== "Void") {
			frm.add_custom_button(__("Resync Tags"), () => {
				frm.call("resync_tags").then(() => {
					frappe.show_alert({ message: __("Tags resynced"), indicator: "green" });
					frm.reload_doc();
				});
			});
		}
	},
});
