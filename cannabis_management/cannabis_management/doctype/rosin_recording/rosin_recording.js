// ── Calculated fields in the child table (always read-only via JS) ────────
const CALCULATED_FIELDS = [
	"total_hash",
	"total_rosin",
	"pounds_ran",
	"yield_to_hash",
	"hash_to_rosin_",
	"subprime_total_tolled",
	"prime_inventory_total_tolled",
	"yield_",
	"actual_yield_to_hash",
	"actual_rosin_yield",
	"raw_material_quantity"
];

// ── Parent form: setup grid + fetch stock balance from master-level fields ──
frappe.ui.form.on("Rosin Recording", {
	onload(frm) {
		setup_grid(frm);

		const filter = { company: "Motley Terpz" };
		const tolling_filter = { company: "Motley Terpz", warehouse_type: "Tolling Partner" };

		// Parent fields
		frm.set_query("batch", () => ({ filters: filter }));
		frm.set_query("tolling_partner", () => ({ filters: tolling_filter }));
		frm.set_query("target_warehouse", () => ({ filters: filter }));
		frm.set_query("expense_account", () => ({
			filters: { company: "Motley Terpz", is_group: 0 }
		}));

		// Child table fields
		frm.set_query("batch_no", "lab_tolling_data", () => ({ filters: filter }));
		frm.set_query("source_bloom", "lab_tolling_data", () => ({ filters: tolling_filter }));
		frm.set_query("prime_strain", "lab_tolling_data", () => ({ filters: {} }));
		frm.set_query("subprime_strain", "lab_tolling_data", () => ({ filters: {} }));
	},
	refresh(frm) {
		setup_grid(frm);

		// Show "Physical Verification" button only after submission
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Physical Verification"), function () {
				create_physical_inventory_verification(frm);
			});
		}
	},

	// ── Auto-fetch stock balance when parent-level batch changes ──
	batch(frm) {
		fetch_stock_balance_items(frm);
	},

	// ── Auto-fetch stock balance when parent-level tolling_partner changes ──
	tolling_partner(frm) {
		fetch_stock_balance_items(frm);
		fetch_expense_account(frm);
	},

	// ── Recalculate tolling_partner_charges when rate changes ──
	rate_tolling_partner(frm) {
		calculate_tolling_partner_charges(frm);
	},

	// Refresh all rows when parent expected_rosin_yield changes
	expected_rosin_yield(frm) {
		(frm.doc.lab_tolling_data || []).forEach(row => {
			frappe.model.set_value(row.doctype, row.name, "expected_rosin_yield", frm.doc.expected_rosin_yield);
			recalculate(frm, row.doctype, row.name);
		});
	},
});

function setup_grid(frm) {
	// Make calculated fields read-only using the standard ERPNext API
	CALCULATED_FIELDS.forEach(fieldname => {
		frappe.meta.get_docfield("Lab Tolling Data", fieldname, frm.doc.name).read_only = 1;
	});
}

// ── Fetch expense account from warehouse's custom_expense_account field ──
function fetch_expense_account(frm) {
	const tolling_partner = frm.doc.tolling_partner;
	if (!tolling_partner) {
		frm.set_value("expense_account", "");
		return;
	}

	frappe.db.get_value("Warehouse", tolling_partner, "custom_expense_account", (r) => {
		if (r && r.custom_expense_account) {
			frm.set_value("expense_account", r.custom_expense_account);
		} else {
			frm.set_value("expense_account", "");
		}
	});
}

// ── Calculate total_quantity (sum of pounds_sent across child rows) ──
function calculate_total_quantity(frm) {
	let total = 0;
	(frm.doc.lab_tolling_data || []).forEach(row => {
		total += flt(row.pounds_sent);
	});
	frm.set_value("total_quantity", flt(total, 4));
}

// ── Calculate tolling_partner_charges = total_quantity * rate_tolling_partner ──
function calculate_tolling_partner_charges(frm) {
	const total_qty = flt(frm.doc.total_quantity);
	const rate = flt(frm.doc.rate_tolling_partner);
	frm.set_value("tolling_partner_charges", flt(total_qty * rate, 2));
}

// ── Child table: trigger recalculation on every manual input change ────────
frappe.ui.form.on("Lab Tolling Data", {

	// When a new row is added, calculations will run as fields are filled
	lab_tolling_data_add(frm, cdt, cdn) {
		// No manual lock needed as fields are handled via setup_grid
	},

	// When a row is removed, recalculate total_quantity
	lab_tolling_data_remove(frm, cdt, cdn) {
		calculate_total_quantity(frm);
		calculate_tolling_partner_charges(frm);
	},

	// Pounds sent drives total_quantity
	pounds_sent: (frm, cdt, cdn) => {
		calculate_total_quantity(frm);
		calculate_tolling_partner_charges(frm);
	},

	// Hash micron fields
	"150u_hash": (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"120u_hash": (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"90u_hash": (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"73u_hash": (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"45u_hash": (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"25u_hash_copy": (frm, cdt, cdn) => recalculate(frm, cdt, cdn),

	// Rosin micron fields
	"150u_rosin": (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"120u_rosin": (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"90u_rosin": (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"73u_rosin": (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"45u_rosin": (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"25u_rosin": (frm, cdt, cdn) => recalculate(frm, cdt, cdn),

	// Amount Ran Grams drives Pounds Ran and all yield percentages
	amount_ran_grams: (frm, cdt, cdn) => recalculate(frm, cdt, cdn),

	// Yield expectations drive raw_material_quantity
	expected__yield__to_hash: (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	expected_hash_yield: (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	expected_rosin_yield: (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
});


// ── Fetch stock balance items using parent-level fields ───────────────────
let _fetching_stock_balance = false;

function fetch_stock_balance_items(frm) {
	// Prevent re-entry
	if (_fetching_stock_balance) return;

	const batch = frm.doc.batch;
	const tolling_partner = frm.doc.tolling_partner;

	// Wait until both parent-level fields are set
	if (!batch || !tolling_partner) return;

	_fetching_stock_balance = true;

	frappe.call({
		method: "cannabis_management.cannabis_management.doctype.rosin_recording.rosin_recording.get_stock_balance_items",
		args: {
			project: batch,
			warehouse: tolling_partner,
		},
		callback: function (r) {
			if (!r.message || r.message.length === 0) {
				_fetching_stock_balance = false;
				frappe.msgprint(__("No items with stock balance found for the selected Batch and Tolling Partner."));
				return;
			}

			// Clear existing child table rows before populating
			frm.doc.lab_tolling_data = [];

			// Add a new row for each item returned
			r.message.forEach((item) => {
				const new_row = frm.add_child("lab_tolling_data");
				new_row.strain_name = item.item_code;
				new_row.batch_no = batch;
				new_row.source_bloom = tolling_partner;
				new_row.date_transferred = item.posting_date;
				new_row.pounds_sent = item.bal_qty;
				new_row.expected_rosin_yield = frm.doc.expected_rosin_yield;
			});

			frm.refresh_field("lab_tolling_data");
			calculate_total_quantity(frm);
			calculate_tolling_partner_charges(frm);
			_fetching_stock_balance = false;
		},
	});
}


// ── Core calculation logic for a single child row ─────────────────────────
function recalculate(frm, cdt, cdn) {
	const row = locals[cdt][cdn];

	// Helper: safely parse a row field value as float
	const f = (fieldname) => parseFloat(row[fieldname]) || 0;

	// 1. Total Hash = sum of all hash micron fields
	const micronsTotalHash =
		f("150u_hash") +
		f("120u_hash") +
		f("90u_hash") +
		f("73u_hash") +
		f("45u_hash") +
		f("25u_hash_copy");

	const totalHash = micronsTotalHash || f("total_hash");

	// 2. Total Rosin = sum of all rosin micron fields
	const micronsTotalRosin =
		f("150u_rosin") +
		f("120u_rosin") +
		f("90u_rosin") +
		f("73u_rosin") +
		f("45u_rosin") +
		f("25u_rosin");

	const totalRosin = micronsTotalRosin || f("total_rosin");

	// 3. Pounds Ran = Amount Ran Grams / 453.592
	const amountRanGrams = f("amount_ran_grams");
	const poundsRan = amountRanGrams
		? parseFloat((amountRanGrams / 453.592).toFixed(4))
		: 0;

	// 4. Yield to Hash % = (Total Hash / Amount Ran Grams) * 100
	const yieldToHash = amountRanGrams
		? ((totalHash / amountRanGrams) * 100).toFixed(2) + "%"
		: "0%";

	// 5. Hash to Rosin % = (Total Rosin / Total Hash) * 100
	const hashToRosin = totalHash
		? parseFloat(((totalRosin / totalHash) * 100).toFixed(2))
		: 0;

	// NOTE: rosin_yield_ is manually entered — not calculated here

	// 6. Actual Yield to Hash % = (Total Hash / Amount Ran Grams) * 100
	const actualYieldToHash = amountRanGrams
		? parseFloat(((totalHash / amountRanGrams) * 100).toFixed(2))
		: 0;

	// 7. Subprime Total Tolled = 45u Rosin + 150u Rosin
	const subprime = f("45u_rosin") + f("150u_rosin");

	// 8. Prime Inventory Total Tolled = 25u Rosin + 73u Rosin + 90u Rosin + 120u Rosin
	const prime = f("25u_rosin") + f("73u_rosin") + f("90u_rosin") + f("120u_rosin");

	// 9. Yield % = (Total Rosin / Total Hash) * 100
	const yieldPct = totalHash
		? parseFloat(((totalRosin / totalHash) * 100).toFixed(2))
		: 0;

	// 10. Actual Rosin Yield % = (Total Rosin / Total Hash) * 100
	const actualRosinYield = totalHash
		? parseFloat(((totalRosin / totalHash) * 100).toFixed(2))
		: 0;

	// 11. Raw Material Quantity (Pounds) using Actual Yields
	let rawMaterialQty = f("pounds_ran");
	if (actualYieldToHash > 0 && actualRosinYield > 0) {
		rawMaterialQty = totalHash / (actualYieldToHash / 100) / 453.592 / (actualRosinYield / 100);
	}

	// Fallback/Ensure not zero
	if (rawMaterialQty <= 0 && (totalHash > 0 || f("pounds_ran") > 0)) {
		rawMaterialQty = f("pounds_ran") || 0;
	}

	// Cap at pounds_sent if calculation exceeds it
	const poundsSent = f("pounds_sent");
	if (rawMaterialQty > poundsSent && poundsSent > 0) {
		rawMaterialQty = poundsSent;
	}

	// ── Write calculated values directly to the child row ─────────────────
	const updates = {
		total_hash: totalHash,
		total_rosin: totalRosin,
		pounds_ran: poundsRan,
		yield_to_hash: yieldToHash,
		hash_to_rosin_: hashToRosin,
		actual_yield_to_hash: actualYieldToHash,
		actual_rosin_yield: actualRosinYield,
		subprime_total_tolled: String(subprime),
		prime_inventory_total_tolled: String(prime),
		yield_: yieldPct,
		raw_material_quantity: flt(rawMaterialQty, 4),
	};

	Object.entries(updates).forEach(([field, value]) => {
		frappe.model.set_value(cdt, cdn, field, value);
	});

	frm.fields_dict["lab_tolling_data"].grid.refresh();
}


// ── Create a draft Physical Inventory Verification from this Rosin Recording ──
function create_physical_inventory_verification(frm) {
	const child_rows = [];

	(frm.doc.lab_tolling_data || []).forEach(row => {
		child_rows.push({
			prime_strain: row.prime_strain,
			subprime_strain: row.subprime_strain,
			subprime_total_tolled: parseFloat(row.subprime_total_tolled) || 0,
			prime_inventory_total_tolled: parseFloat(row.prime_inventory_total_tolled) || 0,
		});
	});

	if (child_rows.length === 0) {
		frappe.msgprint(__("No child table rows found to create Physical Inventory Verification."));
		return;
	}

	frappe.new_doc("Physical Inventory Verification", {
		batch: frm.doc.batch,
		tolling_partner: frm.doc.tolling_partner,
		verification_date: frappe.datetime.get_today(),
		custom_rosin_recording_reference: frm.doc.name,
		physical_inventory_verification_child: child_rows
	});
}
