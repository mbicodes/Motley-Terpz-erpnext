// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Plant Batch", {
	refresh(frm) {
		set_scoping_queries(frm);
		recalc(frm);
	},

	strain(frm) {
		suggest_batch_name(frm);
	},

	planting_date(frm) {
		suggest_batch_name(frm);
		recalc(frm);
	},

	location(frm) {
		// Licence is scoped to the company that owns the selected room.
		set_licence_query(frm);
	},

	plant_count(frm) {
		recalc(frm);
	}
});

// ── event log child tables ────────────────────────────────────────────────
["Plant Batch Growth Phase Change", "Plant Batch Packaging", "Plant Batch Loss Log", "Plant Batch Input Log"].forEach(
	(cdt) => {
		frappe.ui.form.on(cdt, {
			qty: (frm) => recalc(frm),
			qty_lost: (frm) => recalc(frm),
			cost: (frm) => recalc(frm),
		});
	}
);
["growth_phase_log", "packaging_log", "loss_log", "input_log"].forEach((tbl) => {
	const on = {};
	on[tbl + "_add"] = (frm) => recalc(frm);
	on[tbl + "_remove"] = (frm) => recalc(frm);
	frappe.ui.form.on("Plant Batch", on);
});

function suggest_batch_name(frm) {
	if (!frm.doc.batch_name && frm.doc.strain) {
		const parts = [frm.doc.strain, frm.doc.planting_date].filter(Boolean);
		frm.set_value("batch_name", parts.join(" "));
	}
}

function set_scoping_queries(frm) {
	// Location: cultivation rooms only.
	frm.set_query("location", () => ({ filters: { is_cultivation_room: 1 } }));
	// Source Plant: mother plants only.
	frm.set_query("source_plant", () => ({ filters: { is_mother: 1 } }));
	set_licence_query(frm);
}

function set_licence_query(frm) {
	if (frm.doc.location) {
		frappe.db.get_value("Warehouse", frm.doc.location, "company").then((r) => {
			const company = r && r.message && r.message.company;
			frm.set_query("licence", () => (company ? { filters: { company } } : {}));
		});
	} else {
		frm.set_query("licence", () => ({}));
	}
}

function recalc(frm) {
	const initial = cint(frm.doc.plant_count);

	const promoted = (frm.doc.growth_phase_log || []).reduce((s, r) => s + cint(r.qty), 0);
	const destroyed = (frm.doc.loss_log || []).reduce((s, r) => s + cint(r.qty_lost), 0);
	const packaged = (frm.doc.packaging_log || []).reduce((s, r) => s + cint(r.qty), 0);
	const live = Math.max(0, initial - promoted - destroyed - packaged);

	frm.set_value("plants_promoted", promoted);
	frm.set_value("plants_destroyed", destroyed);
	frm.set_value("plants_packaged", packaged);
	frm.set_value("plants_live", live);
	frm.set_value("status", initial && live === 0 ? "Inactive" : "Active");

	frm.set_value(
		"age_days",
		frm.doc.planting_date ? frappe.datetime.get_day_diff(frappe.datetime.now_date(), frm.doc.planting_date) : 0
	);

	frm.set_value("total_input_cost", (frm.doc.input_log || []).reduce((s, r) => s + flt(r.cost), 0));
}
