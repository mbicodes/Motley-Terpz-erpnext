// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Additive Application", {
	refresh(frm) {
		set_target_query(frm);
	},

	applied_to_type(frm) {
		// Re-scope every target row to the chosen type.
		(frm.doc.targets || []).forEach((r) => {
			frappe.model.set_value(r.doctype, r.name, "target_doctype", frm.doc.applied_to_type);
			frappe.model.set_value(r.doctype, r.name, "target_name", null);
		});
		set_target_query(frm);
	}
});

frappe.ui.form.on("Additive Application Target", {
	targets_add(frm, cdt, cdn) {
		if (frm.doc.applied_to_type) {
			frappe.model.set_value(cdt, cdn, "target_doctype", frm.doc.applied_to_type);
		}
	}
});

frappe.ui.form.on("Additive Application Line", {
	item(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.item && !row.additive_template) {
			// Default to the most recent template used with this item.
			frappe.db
				.get_list("Additive Application Line", {
					filters: { item: row.item, additive_template: ["is", "set"] },
					fields: ["additive_template"],
					order_by: "creation desc",
					limit: 1,
				})
				.then((r) => {
					if (r && r.length && r[0].additive_template) {
						frappe.model.set_value(cdt, cdn, "additive_template", r[0].additive_template);
					}
				});
		}
	}
});

function set_target_query(frm) {
	frm.set_query("target_name", "targets", () => {
		if (frm.doc.applied_to_type === "Plant Batch") {
			return { filters: { docstatus: 1 } };
		}
		if (frm.doc.applied_to_type === "Plant") {
			return { filters: { status: "Active" } };
		}
		return {};
	});
}
