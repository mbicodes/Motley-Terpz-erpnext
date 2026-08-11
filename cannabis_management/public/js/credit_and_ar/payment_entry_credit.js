// Payment Entry — two ledgers, never netted.
//
// A customer on a payment plan runs two books at once. Auto-allocation happily
// spreads a receipt across both, which is exactly what the policy forbids, so
// it is switched off for plan customers and the split is made deliberate.

frappe.ui.form.on("Payment Entry", {
	refresh(frm) {
		render_plan_banner(frm);
	},

	party(frm) {
		render_plan_banner(frm);
	},

	payment_type(frm) {
		render_plan_banner(frm);
	},

	custom_ledger(frm) {
		if (["Deposit", "Workout Paydown"].includes(frm.doc.custom_ledger)) {
			frm.clear_table("references");
			frm.refresh_field("references");
			frappe.show_alert({
				message: __("{0} receipts sit against the Sales Order, not an invoice.", [
					frm.doc.custom_ledger,
				]),
				indicator: "blue",
			});
		}
	},
});

function is_customer_receipt(frm) {
	return (
		frm.doc.payment_type === "Receive" &&
		frm.doc.party_type === "Customer" &&
		frm.doc.party
	);
}

function render_plan_banner(frm) {
	frm.dashboard.clear_headline();
	if (!is_customer_receipt(frm)) return;

	frappe.call({
		method: "cannabis_management.credit_and_ar.payment_entry_hooks.get_plan_context",
		args: { customer: frm.doc.party },
		callback: ({ message }) => {
			if (!message || !message.plan) return;

			// Auto-allocation would net plan money against the new book.
			if (frm.doc.docstatus === 0 && frm.doc.allocate_payment_amount) {
				frm.set_value("allocate_payment_amount", 0);
			}

			const missed = message.plan.missed_installments || 0;
			frm.dashboard.set_headline(
				__(
					"{0} is on payment plan {1}{2}. Choose the ledger deliberately — plan money and new-book money are never netted.",
					[
						frm.doc.party,
						message.plan.name,
						missed ? __(" with {0} missed installment(s)", [missed]) : "",
					]
				),
				missed ? "red" : "orange"
			);
		},
	});
}
