// TSBC Ranch — Teardown weight entry (Section 7).
//  • Scan Tag       — scan a physical tag; focuses that row's Weight field.
//  • Total Weights  — enter one combined weight for a strain; splits evenly
//                     across every Teardown Tag row of that strain.

frappe.ui.form.on("Teardown", {
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Scan Tag → Weight"), () => scan_tag(frm), __("Weights"));
			frm.add_custom_button(__("Total Weights (by strain)"), () => total_weights(frm), __("Weights"));
		}
	},
});

frappe.ui.form.on("Teardown Tag", {
	metric_tag(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.metric_tag) return;
		frappe.db.get_value("Metric Tag", row.metric_tag, ["item_code", "growth_stage"]).then((r) => {
			const v = r.message || {};
			frappe.model.set_value(cdt, cdn, "strain", v.item_code || "");
			if (v.growth_stage !== "Flowering") {
				frappe.msgprint(__("Warning: tag {0} is '{1}', not Flowering — it will be rejected on submit.",
					[row.metric_tag, v.growth_stage || __("unset")]));
			}
		});
	},
});

function scan_tag(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Scan Tag"),
		fields: [{ fieldname: "tag", label: __("Tag Code"), fieldtype: "Data", reqd: 1 }],
		primary_action_label: __("Find"),
		primary_action(values) {
			const scanned = (values.tag || "").trim();
			const row = (frm.doc.teardown_tags || []).find(
				(r) => r.metric_tag === scanned || (r.metric_tag && r.metric_tag.endsWith(scanned))
			);
			if (!row) {
				frappe.msgprint(__("Tag {0} is not on this Teardown. Add it first.", [scanned]));
				return;
			}
			d.hide();
			frm.scroll_to_field ? frm.scroll_to_field("teardown_tags") : null;
			const grid_row = frm.fields_dict.teardown_tags.grid.grid_rows_by_docname[row.name];
			if (grid_row) {
				grid_row.toggle_view(true);
				setTimeout(() => {
					const f = grid_row.on_grid_fields_dict
						? grid_row.on_grid_fields_dict.weight
						: null;
					if (f && f.$input) f.$input.focus();
				}, 300);
			}
		},
	});
	d.show();
}

function total_weights(frm) {
	const strains = [...new Set((frm.doc.teardown_tags || []).map((r) => r.strain).filter(Boolean))];
	if (!strains.length) {
		frappe.msgprint(__("Add tags (with strains) before distributing weights."));
		return;
	}
	const d = new frappe.ui.Dialog({
		title: __("Total Weights"),
		fields: [
			{ fieldname: "strain", label: __("Strain"), fieldtype: "Select", options: strains, reqd: 1 },
			{ fieldname: "total_weight", label: __("Total Weight"), fieldtype: "Float", reqd: 1 },
		],
		primary_action_label: __("Distribute Evenly"),
		primary_action(values) {
			const rows = (frm.doc.teardown_tags || []).filter((r) => r.strain === values.strain);
			if (!rows.length) return;
			const per = values.total_weight / rows.length;
			rows.forEach((r) => frappe.model.set_value(r.doctype, r.name, "weight", per));
			frappe.show_alert({
				message: __("{0} split across {1} rows ({2} each).",
					[values.total_weight, rows.length, per.toFixed(2)]),
				indicator: "green",
			});
			d.hide();
		},
	});
	d.show();
}
