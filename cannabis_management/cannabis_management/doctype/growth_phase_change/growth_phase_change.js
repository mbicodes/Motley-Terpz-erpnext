frappe.ui.form.on("Growth Phase Change", {
	refresh(frm) {
		set_queries(frm);
	},

	change_type(frm) {
		set_queries(frm);
	}
});

function set_queries(frm) {
	frm.set_query("source_plant_batch", () => ({ filters: { plants_live: [">", 0] } }));

	frm.set_query("plant", "plants", () => ({ filters: { status: "Active" } }));
}
