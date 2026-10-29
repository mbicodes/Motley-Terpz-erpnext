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

frappe.ui.form.on("All Lab Tolling Data", {
	onload(frm) {
		setup_grid(frm);
	},
	refresh(frm) {
		setup_grid(frm);
	},

	batch_no(frm) {
		fetch_stock_balance_items(frm);
	},

	source_bloom(frm) {
		fetch_stock_balance_items(frm);
	},
});

function setup_grid(frm) {
	CALCULATED_FIELDS.forEach(fieldname => {
		frappe.meta.get_docfield("Lab Tolling Data", fieldname, frm.doc.name).read_only = 1;
	});
}

frappe.ui.form.on("Lab Tolling Data", {

	lab_tolling_data_add(frm, cdt, cdn) {
	},

	"150u_hash":     (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"120u_hash":     (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"90u_hash":      (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"73u_hash":      (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"45u_hash":      (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"25u_hash_copy": (frm, cdt, cdn) => recalculate(frm, cdt, cdn),

	"150u_rosin":    (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"120u_rosin":    (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"90u_rosin":     (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"73u_rosin":     (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"45u_rosin":     (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
	"25u_rosin":     (frm, cdt, cdn) => recalculate(frm, cdt, cdn),

	amount_ran_grams: (frm, cdt, cdn) => recalculate(frm, cdt, cdn),
});

let _fetching_stock_balance = false;

function fetch_stock_balance_items(frm) {
	if (_fetching_stock_balance) return;

	const batch_no = frm.doc.batch_no;
	const source_bloom = frm.doc.source_bloom;

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

			frm.doc.lab_tolling_data = [];

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

function recalculate(frm, cdt, cdn) {
	const row = locals[cdt][cdn];

	const f = (fieldname) => parseFloat(row[fieldname]) || 0;

	const totalHash =
		f("150u_hash") +
		f("120u_hash") +
		f("90u_hash")  +
		f("73u_hash")  +
		f("45u_hash")  +
		f("25u_hash_copy");

	const totalRosin =
		f("150u_rosin") +
		f("120u_rosin") +
		f("90u_rosin")  +
		f("73u_rosin")  +
		f("45u_rosin")  +
		f("25u_rosin");

	const amountRanGrams = f("amount_ran_grams");
	const poundsRan = amountRanGrams
		? parseFloat((amountRanGrams / 453.592).toFixed(4))
		: 0;

	const yieldToHash = amountRanGrams
		? ((totalHash / amountRanGrams) * 100).toFixed(2) + "%"
		: "0%";

	const hashToRosin = totalHash
		? parseFloat(((totalRosin / totalHash) * 100).toFixed(2))
		: 0;

	const subprime = f("45u_rosin") + f("150u_rosin");

	const prime = f("73u_rosin") + f("90u_rosin");

	const yieldPct = totalHash
		? parseFloat(((totalRosin / totalHash) * 100).toFixed(2))
		: 0;

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
