// Data Export dialog presets: adds a button next to Select All / Select
// Mandatory / Unselect All that ticks a saved column set in one click.
//
// frappe.data_import.DataExporter lives in data_import_tools.bundle.js, which
// Frappe loads lazily (frappe.require) when the dialog is first opened, so we
// patch the class the moment the bundle assigns it via a property setter.
//
// The exporter writes columns in the order boxes were ticked, so each preset's
// fieldnames are listed in the exact column order of the target file.
(function () {
	const PRESETS = {
		"Sales Invoice": {
			label: "Select Invoice Sheet Columns",
			fields: {
				"Sales Invoice": [
					"name",
					"naming_series",
					"company",
					"posting_date",
					"currency",
					"conversion_rate",
					"selling_price_list",
					"price_list_currency",
					"plc_conversion_rate",
					"base_net_total",
					"base_grand_total",
					"grand_total",
					"debit_to",
					"customer",
					"customer_name",
					"total_qty",
				],
				items: [
					"name",
					"amount",
					"base_amount",
					"cost_center",
					"income_account",
					"item_name",
					"rate",
					"base_rate",
					"uom",
					"conversion_factor",
					"item_code",
					"item_group",
					"qty",
				],
			},
		},
	};

	function apply_preset(exporter, preset) {
		exporter.unselect_all();
		const missing = [];
		for (const [fieldname, values] of Object.entries(preset.fields)) {
			const field = exporter.dialog.get_field(fieldname);
			values.forEach((value) => {
				const $checkbox = field && field.$wrapper.find(`:checkbox[data-unit="${value}"]`);
				if ($checkbox && $checkbox.length) {
					$checkbox.prop("checked", true).trigger("change");
				} else {
					missing.push(`${fieldname}.${value}`);
				}
			});
		}
		if (missing.length) {
			frappe.msgprint(__("These columns were not found: {0}", [missing.join(", ")]));
		}
	}

	function patch(cls) {
		if (!cls || cls.__cm_presets_patched) return cls;
		const make_select_all_buttons = cls.prototype.make_select_all_buttons;
		cls.prototype.make_select_all_buttons = function () {
			make_select_all_buttons.apply(this, arguments);
			const preset = PRESETS[this.doctype];
			if (!preset) return;
			const $button = $(`<button type="button" class="btn btn-primary btn-xs"></button>`)
				.text(__(preset.label))
				.on("click", (e) => {
					e.preventDefault();
					apply_preset(this, preset);
				});
			this.dialog
				.get_field("select_all_buttons")
				.$wrapper.find('[data-action="unselect_all"]')
				.after(" ", $button);
		};
		cls.__cm_presets_patched = true;
		return cls;
	}

	frappe.provide("frappe.data_import");
	let DataExporter = patch(frappe.data_import.DataExporter);
	Object.defineProperty(frappe.data_import, "DataExporter", {
		configurable: true,
		enumerable: true,
		get: () => DataExporter,
		set: (cls) => {
			DataExporter = patch(cls);
		},
	});
})();
