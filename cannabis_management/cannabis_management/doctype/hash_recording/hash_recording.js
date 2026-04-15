frappe.ui.form.on("Hash Recording", {
	onload(frm) {
		const filter = { company: "Motley Terpz" };
		const tolling_filter = { company: "Motley Terpz", warehouse_type: "Tolling Partner" };

		// Parent fields
		frm.set_query("batchproject", () => ({ filters: filter }));
		frm.set_query("tolling_partner", () => ({ filters: tolling_filter }));

		// Child table fields
		frm.set_query("batchproject", "table_smqw", () => ({ filters: filter }));
		frm.set_query("tooling_partner", "table_smqw", () => ({ filters: tolling_filter }));
	},
	refresh(frm) {
		// ── After submission: show status indicator and Rosin Recording button ──
		if (frm.doc.docstatus === 1) {
			frappe.call({
				method: "cannabis_management.cannabis_management.doctype.hash_recording.hash_recording.get_hash_recording_status",
				args: { hash_recording_name: frm.doc.name },
				async: false,
				callback: function (r) {
					if (!r.message) return;
					const status = r.message;

					frm.page.set_indicator(status, {
						"Submitted": "blue",
						"Rosin Created": "green",
					}[status] || "blue");

					// Show Rosin Recording button only if no Rosin Recording exists yet
					if (status === "Submitted") {
						frm.add_custom_button(__("Rosin Recording"), function () {
							frappe.call({
								method: "cannabis_management.cannabis_management.doctype.hash_recording.hash_recording.create_rosin_recording",
								args: {
									hash_recording_name: frm.doc.name,
								},
								freeze: true,
								freeze_message: __("Creating Rosin Recording …"),
								callback: function (r2) {
									if (r2.message) {
										// Navigate directly to the new Rosin Recording draft
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

	// Auto-fetch stock balance when parent-level batchproject changes
	batchproject(frm) {
		fetch_stock_balance_items(frm);
	},

	// Auto-fetch stock balance when parent-level tolling_partner changes
	tolling_partner(frm) {
		fetch_stock_balance_items(frm);
	},

	// Recalculate tolling_partner_charges when rate changes
	rate_tolling_partner(frm) {
		calculate_tolling_partner_charges(frm);
	},

	// Sync expected_hash_yield to child rows when changed at master level
	expected_hash_yield(frm) {
		(frm.doc.table_smqw || []).forEach(row => {
			frappe.model.set_value(row.doctype, row.name, "expected_yield_to_hash", frm.doc.expected_hash_yield);
		});
	},
});

function calculate_tolling_partner_charges(frm) {
	const total_qty = flt(frm.doc.total_quantity);
	const rate = flt(frm.doc.rate_tolling_partner);
	frm.set_value("tolling_partner_charges", flt(total_qty * rate, 2));
}

frappe.ui.form.on("Hash Recording Child", {
	"150u_hash": (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"120u_hash": (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"90u_hash": (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"73u_hash": (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"45u_hash": (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"25u_hash_copy": (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	amount_ran_grams: (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	pound_sent: (frm, cdt, cdn) => calculate_total_quantity(frm),
	table_smqw_remove: (frm, cdt, cdn) => calculate_total_quantity(frm),
});

function recalculate(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	const f = (fieldname) => flt(row[fieldname]);

	// 1. Total Hash = sum of all hash micron fields
	let total_hash = f("150u_hash") + f("120u_hash") + f("90u_hash") + f("73u_hash") + f("45u_hash") + f("25u_hash_copy");
	frappe.model.set_value(cdt, cdn, "total_hash", total_hash);

	// 2. Pounds Ran = Amount Ran Grams / 453.592
	let amount_ran_grams = f("amount_ran_grams");
	let pounds_ran = amount_ran_grams / 453.592;
	frappe.model.set_value(cdt, cdn, "pounds_ran", flt(pounds_ran, 4));

	// 3. Actual Yield to Hash % = (Total Hash / Amount Ran Grams) * 100
	let actual_yield_to_hash = amount_ran_grams ? (total_hash / amount_ran_grams) * 100 : 0;
	frappe.model.set_value(cdt, cdn, "actual_yield_to_hash", flt(actual_yield_to_hash, 2));
}

// ── Calculate total_quantity (sum of pound_sent across child rows) ──
function calculate_total_quantity(frm) {
	let total = 0;
	(frm.doc.table_smqw || []).forEach(row => {
		total += flt(row.pound_sent);
	});
	frm.set_value("total_quantity", flt(total, 4));
	calculate_tolling_partner_charges(frm);
}

let _fetching_stock_balance = false;

function fetch_stock_balance_items(frm) {
	// Prevent re-entry
	if (_fetching_stock_balance) return;

	const project = frm.doc.batchproject;
	const tolling_partner = frm.doc.tolling_partner;

	// Wait until both parent-level fields are set
	if (!project || !tolling_partner) return;

	_fetching_stock_balance = true;

	frappe.call({
		method: "cannabis_management.cannabis_management.doctype.hash_recording.hash_recording.get_stock_balance_items",
		args: {
			project: project,
			warehouse: tolling_partner,
		},
		callback: function (r) {
			if (!r.message || r.message.length === 0) {
				_fetching_stock_balance = false;
				frappe.msgprint(__("No items with stock balance found for the selected Batch and Tolling Partner."));
				return;
			}

			// Clear existing child table rows before populating (table_smqw)
			frm.doc.table_smqw = [];

			// Add a new row for each item returned
			r.message.forEach((item) => {
				const new_row = frm.add_child("table_smqw");
				new_row.strain_name = item.item_code;
				new_row.batchproject = project;
				new_row.tooling_partner = tolling_partner; // Correct spelling for child field
				new_row.date_transferred = item.posting_date;
				new_row.pound_sent = item.bal_qty;        // Correct spelling for child field (no 's')
				new_row.expected_yield_to_hash = frm.doc.expected_hash_yield;
			});

			frm.refresh_field("table_smqw");
			calculate_total_quantity(frm);
			_fetching_stock_balance = false;
		},
	});
}
