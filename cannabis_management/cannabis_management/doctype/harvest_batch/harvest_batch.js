// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Harvest Batch", {
	dry_weight(frm) {
		// Live preview of the derived weights/status; the server recomputes on save.
		const wet = flt(frm.doc.wet_weight);
		const dry = flt(frm.doc.dry_weight);
		frm.set_value("moisture_loss_pct", dry && wet ? ((wet - dry) / wet) * 100 : null);
		const unaccounted = dry - flt(frm.doc.packaged_weight) - flt(frm.doc.waste_weight);
		frm.set_value("unaccounted_weight", unaccounted);
		frm.set_value("yield_per_plant", cint(frm.doc.plant_count) ? dry / cint(frm.doc.plant_count) : 0);
		let status = "Drying";
		if (dry) {
			if (Math.abs(unaccounted) <= 0.01) status = "Finished";
			else if (flt(frm.doc.packaged_weight) > 0) status = "Partially Packaged";
			else status = "Dried";
		}
		frm.set_value("status", status);
	},
});
