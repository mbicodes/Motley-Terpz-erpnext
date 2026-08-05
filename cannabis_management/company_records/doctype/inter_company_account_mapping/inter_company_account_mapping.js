// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Inter Company Account Mapping", {
	setup(frm) {
		frm.set_query("due_from_account", () => ({
			filters: {
				company: frm.doc.paying_company,
				is_group: 0,
			},
		}));

		frm.set_query("due_to_account", () => ({
			filters: {
				company: frm.doc.receiving_company,
				is_group: 0,
			},
		}));
	},

	paying_company(frm) {
		frm.set_value("due_from_account", "");
	},

	receiving_company(frm) {
		frm.set_value("due_to_account", "");
	},
});
