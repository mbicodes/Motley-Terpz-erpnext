frappe.ui.form.on("Item Group", {
	onload: function (frm) {
		frm.set_query("custom_asset_account", "item_group_defaults", function (doc, cdt, cdn) {
			let row = locals[cdt][cdn];
			return {
				filters: {
					company: row.company,
					is_group: 0,
					root_type: "Asset",
				},
			};
		});
	},
});
