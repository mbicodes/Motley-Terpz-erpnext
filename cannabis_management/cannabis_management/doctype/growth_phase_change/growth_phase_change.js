// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Growth Phase Change", {
	refresh(frm) {
		set_queries(frm);
	},

	change_type(frm) {
		set_queries(frm);
	}
});

function set_queries(frm) {
	// Promote from batches that still have live plants.
	frm.set_query("source_plant_batch", () => ({ filters: { plants_live: [">", 0] } }));

	// Plant tag allocations only, still Active.
	frm.set_query("tag_allocation", () => ({ filters: { tag_type: "Plant", status: "Active" } }));

	// Phase-change targets: active plants.
	frm.set_query("plant", "plants", () => ({ filters: { status: "Active" } }));
}
