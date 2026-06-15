// ── Calculated fields in the child table (always read-only via JS) ────────
const CALCULATED_FIELDS = [
	"total_hash",
	"total_rosin",
	"pounds_ran",
	"yield_to_hash",
	"hash_to_rosin_",
	"subprime_total_tolled",
	"prime_inventory_total_tolled",
	"yield_"
];

// ── Parent form: setup grid + fetch stock balance from master-level fields ──
frappe.ui.form.on("All Lab Tolling Data", {
	onload(frm) {
		setup_grid(frm);
	},
	refresh(frm) {
		setup_grid(frm);
	},

	// ── Auto-fetch stock balance when parent-level batch_no changes ──
	batch_no(frm) {
		fetch_stock_balance_items(frm);
	},

	// ── Auto-fetch stock balance when parent-level source_bloom changes ──
	source_bloom(frm) {
		fetch_stock_balance_items(frm);
	},
});

function setup_grid(frm) {
	// Make calculated fields read-only using the standard ERPNext API
	CALCULATED_FIELDS.forEach(fieldname => {
		frappe.meta.get_docfield("Lab Tolling Data", fieldname, frm.doc.name).read_only = 1;
	});
}

// ── Child table: trigger recalculation on every manual input change ────────
frappe.ui.form.on("Lab Tolling Data", {

	// When a new row is added, calculations will run as fields are filled
	lab_tolling_data_add(frm, cdt, cdn) {
		// No manual lock needed as fields are handled via setup_grid
	},

	// Hash micron fields
	"150u_hash":     (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"120u_hash":     (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"90u_hash":      (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"73u_hash":      (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"45u_hash":      (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"25u_hash_copy": (frm, cdt, cdn) => recalculate(frm, cdt, cdn),

	// Rosin micron fields
	"150u_rosin":    (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"120u_rosin":    (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"90u_rosin":     (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"73u_rosin":     (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"45u_rosin":     (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"25u_rosin":     (frm, cdt, cdn) => recalculate(frm, cdt, cdn),

	// Amount Ran Grams drives Pounds Ran and all yield percentages
	amount_ran_grams: (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
});


// ── Fetch stock balance items using parent-level fields ───────────────────
let _fetching_stock_balance = false;

function fetch_stock_balance_items(frm) {
	// Prevent re-entry
	if (_fetching_stock_balance) return;

	const batch_no = frm.doc.batch_no;
	const source_bloom = frm.doc.source_bloom;

	// Wait until both parent-level fields are set
	if (!batch_no || !source_bloom) return;

	_fetching_stock_balance = true;

	frappe.call({
		method: "cannabis_management.cannabis_management.doctype.all_lab_tolling_data.all_lab_tolling_data.get_stock_balance_items",
		args: {
			project: batch_no,
			warehouse: source_bloom,
		},
		callback: function (r) {
			if (!r.message || r.message.length === 0) {
				_fetching_stock_balance = false;
				frappe.msgprint(__("No items with stock balance found for the selected Batch No and Source Bloom."));
				return;
			}

			// Clear existing child table rows before populating
			frm.doc.lab_tolling_data = [];

			// Add a new row for each item returned
			r.message.forEach((item) => {
				const new_row = frm.add_child("lab_tolling_data");
				new_row.strain_name = item.item_name;
				new_row.batch_no = batch_no;
				new_row.source_bloom = source_bloom;
				new_row.pounds_sent = item.bal_qty;
			});

			frm.refresh_field("lab_tolling_data");
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
	const totalHash =
		f("150u_hash") +
		f("120u_hash") +
		f("90u_hash")  +
		f("73u_hash")  +
		f("45u_hash")  +
		f("25u_hash_copy");

	// 2. Total Rosin = sum of all rosin micron fields
	const totalRosin =
		f("150u_rosin") +
		f("120u_rosin") +
		f("90u_rosin")  +
		f("73u_rosin")  +
		f("45u_rosin")  +
		f("25u_rosin");

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

	// 6. Subprime Total Tolled = 45u Rosin + 150u Rosin
	const subprime = f("45u_rosin") + f("150u_rosin");

	// 7. Prime Inventory Total Tolled = 73u Rosin + 90u Rosin
	const prime = f("73u_rosin") + f("90u_rosin");

	// 8. Yield % = (Total Rosin / Total Hash) * 100
	const yieldPct = totalHash
		? parseFloat(((totalRosin / totalHash) * 100).toFixed(2))
		: 0;

	// ── Write calculated values directly to the child row ─────────────────
	const updates = {
		total_hash:                   totalHash,
		total_rosin:                  totalRosin,
		pounds_ran:                   poundsRan,
		yield_to_hash:                yieldToHash,
		hash_to_rosin_:               hashToRosin,
		subprime_total_tolled:        String(subprime),
		prime_inventory_total_tolled: String(prime),
		yield_:                       yieldPct,
	};

	Object.entries(updates).forEach(([field, value]) => {
		frappe.model.set_value(cdt, cdn, field, value);
	});

	frm.fields_dict["lab_tolling_data"].grid.refresh();
}