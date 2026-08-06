// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Plant Batch", {

	refresh(frm) {
		calculate_totals(frm);
	},

	plant_count(frm) {
		calculate_totals(frm);
	},

	wet_weight(frm) {
		calculate_totals(frm);
	},

	dry_weight(frm) {
		calculate_totals(frm);
	},

	date_transplanted(frm) {
		calculate_totals(frm);
	},

	date_flowering_start(frm) {
		calculate_totals(frm);
	}
});

frappe.ui.form.on("Plant Batch Loss Log", {
	qty_lost(frm) {
		calculate_totals(frm);
	},
	loss_log_add(frm) {
		calculate_totals(frm);
	},
	loss_log_remove(frm) {
		calculate_totals(frm);
	}
});

frappe.ui.form.on("Plant Batch Input Log", {
	cost(frm) {
		calculate_totals(frm);
	},
	input_log_add(frm) {
		calculate_totals(frm);
	},
	input_log_remove(frm) {
		calculate_totals(frm);
	}
});

function calculate_totals(frm) {

	// Plants Lost (sum of Loss Log) + Plants Harvested
	let plants_lost = 0;
	(frm.doc.loss_log || []).forEach(function (row) {
		plants_lost += cint(row.qty_lost);
	});

	frm.set_value("plants_lost", plants_lost);
	frm.set_value("plants_harvested", cint(frm.doc.plant_count) - plants_lost);

	// Total Input Cost (sum of Input / Additive Log)
	let total_input_cost = 0;
	(frm.doc.input_log || []).forEach(function (row) {
		total_input_cost += flt(row.cost);
	});

	frm.set_value("total_input_cost", total_input_cost);

	// Moisture Loss %
	frm.set_value(
		"moisture_loss_pct",
		flt(frm.doc.wet_weight) > 0
			? (flt(frm.doc.wet_weight) - flt(frm.doc.dry_weight)) / flt(frm.doc.wet_weight) * 100
			: 0
	);

	// Waste %
	frm.set_value(
		"waste_pct",
		cint(frm.doc.plant_count) > 0 ? (plants_lost / cint(frm.doc.plant_count)) * 100 : 0
	);

	// Days to Flower
	frm.set_value(
		"days_to_flower",
		(frm.doc.date_transplanted && frm.doc.date_flowering_start)
			? frappe.datetime.get_day_diff(frm.doc.date_flowering_start, frm.doc.date_transplanted)
			: 0
	);

	// Yield per Plant
	let plants_harvested = cint(frm.doc.plant_count) - plants_lost;
	frm.set_value(
		"yield_per_plant",
		plants_harvested > 0 ? flt(frm.doc.dry_weight) / plants_harvested : 0
	);
}
