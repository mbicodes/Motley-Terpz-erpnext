const CYF_GRAMS_PER_LB = 453.59237;

frappe.ui.form.on("Customer Yield Feedback", {
	setup(frm) {
		frm.set_query("sales_order", () => ({
			filters: { docstatus: 1, ...(frm.doc.customer ? { customer: frm.doc.customer } : {}) },
		}));
	},

	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Customer Yield Report"), () =>
				frappe.set_route("query-report", "Customer Yield Report", { customer: frm.doc.customer })
			);
		}
	},

	sales_order(frm) {
		if (!frm.doc.sales_order) return;
		frappe.db.get_value("Sales Order", frm.doc.sales_order, ["customer", "company"]).then(({ message }) => {
			if (message.customer && frm.doc.customer !== message.customer) frm.set_value("customer", message.customer);
			frm.set_value("company", message.company);
		});
		const empty = !(frm.doc.item_yield || []).some((r) => r.item_code);
		if (empty) frm.trigger("get_items_from_sales_order");
	},

	get_items_from_sales_order(frm) {
		frappe.call({
			method: "cannabis_management.cannabis_management.doctype.customer_yield_feedback.customer_yield_feedback.get_sales_order_items",
			args: { sales_order: frm.doc.sales_order },
			callback({ message }) {
				frm.clear_table("item_yield");
				(message || []).forEach((it) => frm.add_child("item_yield", it));
				frm.refresh_field("item_yield");
			},
		});
	},
});

function cyf_calculate(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const raw_g = flt(row.quantity) * CYF_GRAMS_PER_LB;
	if (raw_g && flt(row.hash_qty)) row.yield_percentage = (flt(row.hash_qty) / raw_g) * 100;
	if (flt(row.hash_qty) && flt(row.rosin_qty)) row.hash_to_rosin = (flt(row.rosin_qty) / flt(row.hash_qty)) * 100;
	if (raw_g && flt(row.rosin_qty)) row.rosin_yield = (flt(row.rosin_qty) / raw_g) * 100;
	else if (flt(row.yield_percentage) && flt(row.hash_to_rosin))
		row.rosin_yield = (flt(row.yield_percentage) * flt(row.hash_to_rosin)) / 100;
	else row.rosin_yield = 0;
	frm.refresh_field("item_yield");
}

frappe.ui.form.on("Item Yield", {
	quantity: cyf_calculate,
	hash_qty: cyf_calculate,
	rosin_qty: cyf_calculate,
	yield_percentage: cyf_calculate,
	hash_to_rosin: cyf_calculate,
});
