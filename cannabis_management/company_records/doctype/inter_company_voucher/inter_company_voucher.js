// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Inter Company Voucher", {
	setup(frm) {
		frm.set_query("bank_account", () => ({
			filters: {
				company: frm.doc.paying_company,
				is_group: 0,
			},
		}));
	},

	onload(frm) {
		frm.fields_dict.allocations.grid.get_field("expense_account").get_query = (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return {
				filters: {
					company: row.company,
					is_group: 0,
					root_type: "Expense",
				},
			};
		};

		frm.fields_dict.allocations.grid.get_field("cost_center").get_query = (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return {
				filters: {
					company: row.company,
					is_group: 0,
				},
			};
		};

		frm.fields_dict.allocations.grid.get_field("project").get_query = (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return {
				filters: {
					company: row.company,
				},
			};
		};
	},

	paying_company(frm) {
		frm.set_value("bank_account", "");
		if (frm.doc.paying_company) {
			frappe.db.get_value("Company", frm.doc.paying_company, "default_currency").then((r) => {
				if (r.message && r.message.default_currency) {
					frm.set_value("currency", r.message.default_currency);
				}
			});
		}
	},

	refresh(frm) {
		show_allocation_total(frm);
	},

	validate(frm) {
		show_allocation_total(frm);
	},
});

frappe.ui.form.on("Inter Company Expense Allocation", {
	company(frm, cdt, cdn) {
		frappe.model.set_value(cdt, cdn, "expense_account", "");
		frappe.model.set_value(cdt, cdn, "cost_center", "");
		frappe.model.set_value(cdt, cdn, "project", "");
	},

	amount(frm) {
		show_allocation_total(frm);
	},

	allocations_remove(frm) {
		show_allocation_total(frm);
	},
});

function show_allocation_total(frm) {
	const total = (frm.doc.allocations || []).reduce((sum, row) => sum + flt(row.amount), 0);
	frm.dashboard.clear_headline();
	if (frm.doc.allocations && frm.doc.allocations.length) {
		const matches = Math.abs(total - flt(frm.doc.total_amount)) < 0.005;
		frm.dashboard.set_headline_alert(
			`Allocation total: ${format_currency(total, frm.doc.currency)} ` +
				(matches ? "(matches Total Amount)" : "— does not match Total Amount"),
			matches ? "green" : "orange"
		);
	}
}
