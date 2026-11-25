frappe.ui.form.on("Toll Job", {
	refresh(frm) {
		frm.add_custom_button(__("Toll Processing Board"), () => frappe.set_route("toll-processing-board"));
		if (frm.doc.sales_invoice) {
			frm.add_custom_button(__("Sales Invoice"), () => frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice), __("View"));
		}
		frm.add_custom_button(__("Stock Ledger"), () => frappe.set_route("query-report", "Stock Ledger", {
			company: frm.doc.company, batch_no: frm.doc.batch, from_date: frm.doc.received_date,
		}), __("View"));
		frm.set_query("customer", () => ({ filters: { customer_group: "Toll Clients" } }));
		if (frm.doc.ff_washed_lbs > 0) frm.set_df_property("return_type", "read_only", 1);
		frm.set_intro(frm.is_new() ? __("Receive material from the Toll Processing Board: it creates the job, its batch and the receipt together.") : "");
	},
});
