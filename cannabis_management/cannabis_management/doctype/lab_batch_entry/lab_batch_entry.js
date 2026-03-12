frappe.ui.form.on("Lab Batch Entry", {
	onload(frm) {
		const filter = { company: "Motley Terpz" };
		const tolling_filter = { company: "Motley Terpz", warehouse_type: "Tolling Partner" };

		// Parent fields
		frm.set_query("batchproject", () => ({ filters: filter }));
		frm.set_query("tolling_partner", () => ({ filters: tolling_filter }));

		// Child table fields
		frm.set_query("batch_number", "lab_batch_entry_child", () => ({ filters: filter }));
		frm.set_query("tolling_partner", "lab_batch_entry_child", () => ({ filters: tolling_filter }));
	},
	refresh(frm) {
		// ── Hide/show amount_ran_grams column in child table ──
		const grid = frm.fields_dict.lab_batch_entry_child && frm.fields_dict.lab_batch_entry_child.grid;
		if (grid) {
			if (frm.doc.docstatus === 0) {
				// Hide on draft
				grid.toggle_display("amount_ran_grams", false);
				grid.toggle_display("pounds_ran", false);
				grid.refresh();
			} else {
				// Show after submission
				grid.toggle_display("amount_ran_grams", true);
				grid.toggle_display("pounds_ran", true);
				grid.refresh();
			}
		}

		// ── "Fetch Details" button – visible on draft only ──
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Fetch Details"), function () {
				fetch_stock_balance_items(frm);
			}).addClass("btn-primary");
		}

		// ── After submission: compute status and show action buttons ──
		if (frm.doc.docstatus === 1) {
			frappe.call({
				method: "cannabis_management.cannabis_management.doctype.lab_batch_entry.lab_batch_entry.get_batch_status",
				args: { lab_batch_entry_name: frm.doc.name },
				callback: function (r) {
					if (!r.message) return;
					const batch_status = r.message;

					frm.page.set_indicator(batch_status, {
						"Batch Sent":     "blue",
						"Batch Run":      "yellow",
						"Hash Produced":  "orange",
						"Rosin Produced": "green",
					}[batch_status] || "blue");

					// Hash Recording button: Batch Sent and Batch Run only
					if (batch_status === "Batch Sent" || batch_status === "Batch Run") {
						frm.add_custom_button(__("Hash Recording"), function () {
							frappe.call({
								method: "cannabis_management.cannabis_management.doctype.lab_batch_entry.lab_batch_entry.create_hash_recording",
								args: { lab_batch_entry_name: frm.doc.name },
								freeze: true,
								freeze_message: __("Creating Hash Recording …"),
								callback: function (r2) {
									if (r2.message) {
										frappe.set_route("Form", "Hash Recording", r2.message);
									}
								},
							});
						}, __("Actions"));
					}

					// Rosin Recording button: Hash Produced only
					if (batch_status === "Hash Produced") {
						frm.add_custom_button(__("Rosin Recording"), function () {
							frappe.call({
								method: "cannabis_management.cannabis_management.doctype.lab_batch_entry.lab_batch_entry.create_rosin_recording",
								args: { lab_batch_entry_name: frm.doc.name },
								freeze: true,
								freeze_message: __("Creating Rosin Recording …"),
								callback: function (r2) {
									if (r2.message) {
										frappe.set_route("Form", "Rosin Recording", r2.message);
									}
								},
							});
						}, __("Actions"));
					}
				},
			});
		}
	},
});

frappe.ui.form.on("Lab Batch Entry Child", {
	amount_ran_grams: function (frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		let pounds_ran = flt(row.amount_ran_grams) / 453.592;
		frappe.model.set_value(cdt, cdn, "pounds_ran", flt(pounds_ran, 4));
	},
	pounds_sent: function (frm, cdt, cdn) {
		calculate_total_quantity(frm);
	},
	lab_batch_entry_child_remove: function (frm, cdt, cdn) {
		calculate_total_quantity(frm);
	},
});

// ── Calculate total_quantity (sum of pounds_sent across child rows) ──
function calculate_total_quantity(frm) {
	let total = 0;
	(frm.doc.lab_batch_entry_child || []).forEach(row => {
		total += flt(row.pounds_sent);
	});
	frm.set_value("total_quantity", flt(total, 4));
}

// ─── helper: fetch stock-balance rows ───────────────────────────────────────
let _fetching_stock_balance = false;

function fetch_stock_balance_items(frm) {
	if (_fetching_stock_balance) return;

	const project = frm.doc.batchproject;
	const tolling_partner = frm.doc.tolling_partner;

	if (!project || !tolling_partner) {
		frappe.msgprint(__("Please set both <b>Batch/Project</b> and <b>Tolling Partner</b> before fetching details."));
		return;
	}

	_fetching_stock_balance = true;

	frappe.call({
		method: "cannabis_management.cannabis_management.doctype.lab_batch_entry.lab_batch_entry.get_stock_balance_items",
		args: { project: project, warehouse: tolling_partner },
		callback: function (r) {
			if (!r.message || r.message.length === 0) {
				_fetching_stock_balance = false;
				frappe.msgprint(__("No items with stock balance found for the selected Batch and Tolling Partner."));
				return;
			}

			frm.doc.lab_batch_entry_child = [];

			r.message.forEach((item) => {
				const new_row = frm.add_child("lab_batch_entry_child");
				new_row.strain_name = item.item_code;
				new_row.batch_number = project;
				new_row.tolling_partner = tolling_partner;
				new_row.date_transferred = item.posting_date;
				new_row.pounds_sent = item.bal_qty;
			});

			frm.refresh_field("lab_batch_entry_child");
			frm.dirty();
			calculate_total_quantity(frm);
			_fetching_stock_balance = false;
		},
	});
}