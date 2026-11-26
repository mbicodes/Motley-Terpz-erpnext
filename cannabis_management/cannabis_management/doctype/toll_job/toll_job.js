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
		const can_cancel = frappe.user.has_role(["Production Manager", "System Manager"]);
		if (!frm.is_new() && can_cancel && frm.doc.status !== "Cancelled" && frm.doc.status !== "Invoiced") {
			frm.add_custom_button(__("Cancel Job"), () => frappe.confirm(
				__("Cancel {0}? All its stock entries and delivery notes are cancelled (last step first) and a draft invoice is deleted. Empty batches are deleted; a batch that is not empty is only disabled.", [frm.doc.name]),
				() => frappe.call({ method: "cannabis_management.toll.api.cancel_toll_job", args: { toll_job: frm.doc.name }, freeze: true,
					freeze_message: __("Cancelling {0}…", [frm.doc.name]) }).then(r => {
					frappe.msgprint({ title: __("Toll Job cancelled"), message: r.message.message, indicator: "orange" });
					frm.reload_doc();
				})));
			frm.change_custom_button_type(__("Cancel Job"), null, "danger");
		}
		if (!frm.is_new() && frm.doc.status === "Cancelled" && frappe.model.can_delete("Toll Job")) {
			frm.add_custom_button(__("Delete Job"), () => frappe.confirm(
				__("Permanently delete {0}? Its cancelled stock entries / delivery notes and its empty batches are deleted with it. If a batch is not empty, nothing is deleted.", [frm.doc.name]),
				() => frappe.call({ method: "frappe.client.delete", args: { doctype: "Toll Job", name: frm.doc.name }, freeze: true }).then(() => {
					frappe.show_alert({ message: __("{0} deleted.", [frm.doc.name]), indicator: "green" });
					frappe.set_route("List", "Toll Job");
				})));
			frm.change_custom_button_type(__("Delete Job"), null, "danger");
		}
		if (frm.doc.ff_washed_lbs > 0) frm.set_df_property("return_type", "read_only", 1);
		frm.set_intro(frm.is_new() ? __("Receive material from the Toll Processing Board: it creates the job, its batch and the receipt together.") : "");
	},
});
