// TSBC Ranch — Farm actions on the Batch form.
// "Change Growth Phase" promotes N immature plants to individually tagged
// Vegetative plants, pulling unused tags from the pool (server: farm.change_growth_phase).

frappe.ui.form.on("Batch", {
	refresh(frm) {
		if (frm.is_new()) return;

		const immature = frm.doc.custom_immature_plant_count || 0;
		if (immature > 0) {
			frm.add_custom_button(
				__("Change Growth Phase"),
				() => open_change_phase_dialog(frm),
				__("Farm")
			);
		}

		// Quick "Add Plant Cost" entry pre-filled with nothing (operator picks tags).
		frm.add_custom_button(
			__("New Plant Cost Entry"),
			() => frappe.new_doc("Plant Cost Entry"),
			__("Farm")
		);
	},
});

function open_change_phase_dialog(frm) {
	const immature = frm.doc.custom_immature_plant_count || 0;
	const d = new frappe.ui.Dialog({
		title: __("Change Growth Phase"),
		fields: [
			{
				fieldname: "info",
				fieldtype: "HTML",
				options: `<p>${__("Immature plants available")}: <b>${immature}</b>. ` +
					`${__("Unused tags will be pulled automatically from the pool.")}</p>`,
			},
			{
				fieldname: "num_plants",
				label: __("Number of Plants to Promote"),
				fieldtype: "Int",
				reqd: 1,
				default: immature,
			},
			{
				fieldname: "output_warehouse",
				label: __("Output Warehouse"),
				fieldtype: "Link",
				options: "Warehouse",
				reqd: 1,
				default: frm.doc.custom_default_warehouse || "",
			},
		],
		primary_action_label: __("Promote"),
		primary_action(values) {
			if (values.num_plants > immature) {
				frappe.msgprint(__("Cannot promote more than {0} immature plants.", [immature]));
				return;
			}
			frappe.call({
				method: "cannabis_management.farm.change_growth_phase",
				args: {
					batch: frm.doc.name,
					num_plants: values.num_plants,
					output_warehouse: values.output_warehouse,
				},
				freeze: true,
				freeze_message: __("Promoting plants and assigning tags…"),
				callback(r) {
					if (r.message) {
						frappe.show_alert({
							message: __("{0} plants promoted. {1} immature remaining.", [
								r.message.promoted,
								r.message.immature_remaining,
							]),
							indicator: "green",
						});
						d.hide();
						frm.reload_doc();
					}
				},
			});
		},
	});
	d.show();
}
