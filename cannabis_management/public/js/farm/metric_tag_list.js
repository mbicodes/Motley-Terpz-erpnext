// TSBC Ranch — bulk Farm actions on the Metric Tag list view.
//  • Destroy Plants   — destructive: growth_stage = Destroyed + Plant Waste Log + destroyed_by
//  • Record Waste     — non-destructive: Plant Waste Log only (plant stays alive)

frappe.listview_settings["Metric Tag"] = frappe.listview_settings["Metric Tag"] || {};

const WASTE_FIELDS = (include_reason = true) => [
	{ fieldname: "disposal_method", label: __("Disposal Method"), fieldtype: "Data", reqd: 1 },
	{ fieldname: "waste_weight", label: __("Waste Weight"), fieldtype: "Float" },
	{ fieldname: "waste_uom", label: __("UOM"), fieldtype: "Select", options: ["", "g", "lb", "oz", "kg"] },
	{ fieldname: "cb", fieldtype: "Column Break" },
	{
		fieldname: "waste_reason", label: __("Reason"), fieldtype: "Select",
		options: ["", "Pest", "Disease", "Male Plant", "Environmental", "Other"],
		reqd: include_reason,
	},
	{ fieldname: "logged_by", label: __("Logged By"), fieldtype: "Link", options: "Employee" },
	{ fieldname: "note", label: __("Note"), fieldtype: "Small Text" },
];

function run_bulk(listview, method, title, action_label, indicator) {
	const tags = listview.get_checked_items(true); // names only
	if (!tags.length) {
		frappe.msgprint(__("Select at least one tag first."));
		return;
	}
	const d = new frappe.ui.Dialog({
		title: `${title} (${tags.length})`,
		fields: WASTE_FIELDS(),
		primary_action_label: action_label,
		primary_action(values) {
			frappe.call({
				method,
				args: { tag_names: tags, ...values },
				freeze: true,
				callback(r) {
					if (r.message) {
						frappe.show_alert({ message: __("Done — {0} tags.", [tags.length]), indicator });
						d.hide();
						listview.refresh();
					}
				},
			});
		},
	});
	d.show();
}

frappe.listview_settings["Metric Tag"].onload = function (listview) {
	listview.page.add_actions_menu_item(__("Destroy Plants"), () =>
		run_bulk(listview, "cannabis_management.farm.destroy_plants",
			__("Destroy Plants"), __("Destroy"), "red"), true);

	listview.page.add_actions_menu_item(__("Record Waste (non-destructive)"), () =>
		run_bulk(listview, "cannabis_management.farm.record_waste",
			__("Record Waste"), __("Record Waste"), "orange"), true);
};
