// frappe.ui.form.on("Material Request Item", {
//     item_code(frm, cdt, cdn) {
//         let row = locals[cdt][cdn];
//         if (!row.item_code) return;

//         frappe.call({
//             method: "frappe.client.get",
//             args: { doctype: "Item", name: row.item_code },
//             callback(r) {
//                 if (!r.message) return;
//                 let item = r.message;

//                 let def_supplier = "";
//                 if (item.item_defaults && item.item_defaults.length > 0) {
//                     let def = item.item_defaults.find(d => d.default_supplier);
//                     if (def) def_supplier = def.default_supplier;
//                 }

//                 frappe.model.set_value(cdt, cdn, "breeder", def_supplier || "");
//             }
//         });
//     }
// });


// // ---------------------------------------------------------
// // UPDATE ITEM DEFAULT SUPPLIER ON SAVE (BACKGROUND REFRESH)
// // ---------------------------------------------------------
// frappe.ui.form.on("Material Request", {
//     before_save(frm) {
//         // frappe.msgprint("Updating Item Default Suppliers...");
//         let company = frappe.defaults.get_default("company");

//         (frm.doc.items || []).forEach(row => {

//             if (!row.item_code || !row.breeder) return;

//             frappe.call({
//                 method: "frappe.client.get",
//                 args: { doctype: "Item", name: row.item_code },

//                 callback(res) {
//                     if (!res.message) return;

//                     let item = res.message;

//                     if (!item.item_defaults)
//                         item.item_defaults = [];

//                     let def_row = item.item_defaults.find(d => d.company === company);
//                     let current_default = def_row ? def_row.default_supplier : "";

//                     // Condition A: empty
//                     // Condition B: different
//                     if (!current_default || current_default !== row.breeder) {

//                         if (def_row) {
//                             def_row.default_supplier = row.breeder;
//                         } else {
//                             item.item_defaults.push({
//                                 company: company,
//                                 default_supplier: row.breeder
//                             });
//                         }

//                         frappe.call({
//                             method: "frappe.client.save",
//                             args: { doc: item },
//                             callback() {

//                                 frappe.show_alert(
//                                     `✔ Default Supplier updated: ${row.item_code} → ${row.breeder}`
//                                 );

//                                 // ------------------------------------------------
//                                 // 🔥 BACKGROUND REFRESH (NO ROUTE CHANGE)
//                                 // ------------------------------------------------
//                                 frappe.model.clear_doc("Item", row.item_code);
//                                 frappe.model.with_doc("Item", row.item_code, function() {
//                                     console.log("Item background refreshed:", row.item_code);
//                                 });
//                                 // ------------------------------------------------
//                             }
//                         });
//                     }
//                 }
//             });
//         });
//     }
// });

// Material Request Visibility Logic
frappe.ui.form.on("Material Request", {
	setup: function(frm) {
		hide_initial_fields(frm);
	},
	onload: function(frm) {
		hide_initial_fields(frm);
	},
	refresh: function(frm) {
		hide_initial_fields(frm);
	},
	// This helps with Quick Entry dialogs
	on_make: function(frm) {
		hide_initial_fields(frm);
	}
});

function hide_initial_fields(frm) {
	if (!frm || !frm.doc) return;
	
	console.log("Material Request Visibility Check: State =", frm.doc.workflow_state, "Is New =", frm.is_new());
	
	let state = frm.doc.workflow_state || "";
	let is_draft = state.toLowerCase() === "draft";
	let should_hide = frm.is_new() || is_draft || !state;

	// Targeting fields for both Dialog and Full Form
	if (should_hide) {
		frm.toggle_display("material_request_type", false);
		frm.toggle_display("items", false);
		
		// Disable mandatory requirement if hidden
		frm.set_df_property("material_request_type", "reqd", 0);
		frm.set_df_property("items", "reqd", 0);
	} else {
		frm.toggle_display("material_request_type", true);
		frm.toggle_display("items", true);
		
		// Restore mandatory requirement
		frm.set_df_property("material_request_type", "reqd", 1);
		frm.set_df_property("items", "reqd", 1);
	}
}



