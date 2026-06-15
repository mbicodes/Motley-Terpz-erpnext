// // Lab Tolling Data — Client Script
// // Manual input fields are editable. Calculated fields are read-only always.

// // ── Fields that are ALWAYS read-only (calculated by code) ─────────────────
// const CALCULATED_FIELDS = [
// 	"total_hash",
// 	"total_rosin",
// 	"pounds_ran",
// 	"yield_to_hash",
// 	"hash_to_rosin_",
// 	"subprime_total_tolled",
// 	"prime_inventory_total_tolled",
// 	"yield_"
// ];

// // ── Fields the user manually inputs ───────────────────────────────────────
// // strain_name, batch_no, pounds_sent, source_bloom, run_for,
// // date_transferred, amount_ran_grams,
// // 150u_hash, 120u_hash, 90u_hash, 73u_hash, 45u_hash, 25u_hash_copy,
// // 150u_rosin, 120u_rosin, 90u_rosin, 73u_rosin, 45u_rosin, 25u_rosin,
// // live_resin_produced

// frappe.ui.form.on("Lab Tolling Data", {

// 	// ── On form load / refresh: lock calculated fields immediately ─────────
// 	refresh(frm) {
// 		setCalculatedFieldsReadOnly(frm);

// 		// If editing an existing doc, recalculate to ensure fields are current
// 		if (!frm.is_new()) {
// 			recalculate(frm);
// 		}
// 	},

// 	// ── Trigger recalculation on every manual input field change ──────────

// 	// Hash micron fields
// 	"150u_hash":     (frm) => recalculate(frm),
// 	"120u_hash":     (frm) => recalculate(frm),
// 	"90u_hash":      (frm) => recalculate(frm),
// 	"73u_hash":      (frm) => recalculate(frm),
// 	"45u_hash":      (frm) => recalculate(frm),
// 	"25u_hash_copy": (frm) => recalculate(frm),

// 	// Rosin micron fields
// 	"150u_rosin":    (frm) => recalculate(frm),
// 	"120u_rosin":    (frm) => recalculate(frm),
// 	"90u_rosin":     (frm) => recalculate(frm),
// 	"73u_rosin":     (frm) => recalculate(frm),
// 	"45u_rosin":     (frm) => recalculate(frm),
// 	"25u_rosin":     (frm) => recalculate(frm),

// 	// Amount Ran Grams drives Pounds Ran and all yield percentages
// 	amount_ran_grams: (frm) => recalculate(frm),
// });


// // ── Enforce read-only on all calculated fields ─────────────────────────────
// function setCalculatedFieldsReadOnly(frm) {
// 	CALCULATED_FIELDS.forEach((field) => {
// 		frm.set_df_property(field, "read_only", 1);
// 	});
// 	frm.refresh_fields(CALCULATED_FIELDS);
// }


// // ── Core calculation logic ─────────────────────────────────────────────────
// function recalculate(frm) {
// 	// Helper: safely parse a field value as float
// 	const f = (fieldname) => parseFloat(frm.doc[fieldname]) || 0;

// 	// 1. Total Hash = sum of all hash micron fields
// 	const totalHash =
// 		f("150u_hash") +
// 		f("120u_hash") +
// 		f("90u_hash")  +
// 		f("73u_hash")  +
// 		f("45u_hash")  +
// 		f("25u_hash_copy");

// 	// 2. Total Rosin = sum of all rosin micron fields
// 	const totalRosin =
// 		f("150u_rosin") +
// 		f("120u_rosin") +
// 		f("90u_rosin")  +
// 		f("73u_rosin")  +
// 		f("45u_rosin")  +
// 		f("25u_rosin");

// 	// 3. Pounds Ran = Amount Ran Grams / 453.592
// 	const amountRanGrams = f("amount_ran_grams");
// 	const poundsRan = amountRanGrams
// 		? parseFloat((amountRanGrams / 453.592).toFixed(4))
// 		: 0;

// 	// 4. Yield to Hash % = (Total Hash / Amount Ran Grams) * 100
// 	const yieldToHash = amountRanGrams
// 		? ((totalHash / amountRanGrams) * 100).toFixed(2) + "%"
// 		: "0%";

// 	// 5. Hash to Rosin % = (Total Rosin / Total Hash) * 100
// 	const hashToRosin = totalHash
// 		? parseFloat(((totalRosin / totalHash) * 100).toFixed(2))
// 		: 0;

// 	// 6. Subprime Total Tolled = 45u Rosin + 150u Rosin
// 	const subprime = f("45u_rosin") + f("150u_rosin");

// 	// 8. Prime Inventory Total Tolled = 73u Rosin + 90u Rosin
// 	const prime = f("73u_rosin") + f("90u_rosin");

// 	// 9. Yield % = (Total Rosin / Total Hash) * 100
// 	const yieldPct = totalHash
// 		? parseFloat(((totalRosin / totalHash) * 100).toFixed(2))
// 		: 0;

// 	// ── Set all calculated values directly on the doc ────────────────────
// 	// Using frm.doc + refresh_field keeps fields read-only
// 	// (frappe.model.set_value would briefly unlock them)
// 	const updates = {
// 		total_hash:                   totalHash,
// 		total_rosin:                  totalRosin,
// 		pounds_ran:                   poundsRan,
// 		yield_to_hash:                yieldToHash,
// 		hash_to_rosin_:               hashToRosin,
// 		subprime_total_tolled:        String(subprime),
// 		prime_inventory_total_tolled: String(prime),
// 		yield_:                       yieldPct,
// 	};

// 	Object.entries(updates).forEach(([field, value]) => {
// 		frm.doc[field] = value;
// 	});

// 	// Refresh only the calculated fields so read_only is preserved
// 	frm.refresh_fields(CALCULATED_FIELDS);
// }