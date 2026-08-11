// Sales Order credit gate — buttons, banners and print suppression.
//
// The print suppression here is convenience only. Every print and PDF route is
// guarded server-side in credit_and_ar/print_guard.py; removing these menu
// items just stops people hitting a wall they can see coming.

frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		if (frm.doc.__islocal) return;

		render_credit_banner(frm);
		add_approval_buttons(frm);
		suppress_print(frm);
	},

	custom_mode_of_payment(frm) {
		render_credit_banner(frm);
	},

	customer(frm) {
		if (frm.doc.customer) render_credit_banner(frm);
	},
});

const TERMS = "Payment Terms";
const PENDING = "Pending Approval";
const APPROVED = "Approved";
const REJECTED = "Rejected";

function is_terms(frm) {
	return frm.doc.custom_mode_of_payment === TERMS && frm.doc.custom_sales_order_type !== "Samples";
}

function can_approve() {
	return ["Managing Director", "Ops Manager", "System Manager"].some((role) =>
		frappe.user_roles.includes(role)
	);
}

function add_approval_buttons(frm) {
	if (!is_terms(frm) || frm.doc.docstatus !== 0) return;

	if ([PENDING, APPROVED].indexOf(frm.doc.custom_approval_status) === -1) {
		frm.add_custom_button(__("Request MD Approval"), () => {
			frappe.call({
				method: "cannabis_management.credit_and_ar.api.request_terms_approval",
				args: { sales_order: frm.doc.name },
				freeze: true,
				freeze_message: __("Requesting approval…"),
				callback: () => {
					frappe.show_alert({
						message: __("Approval requested."),
						indicator: "blue",
					});
					frm.reload_doc();
				},
			});
		}).addClass("btn-primary");
	}

	if (frm.doc.custom_approval_status === PENDING && can_approve()) {
		frm.add_custom_button(__("Approve Terms"), () => {
			frappe.prompt(
				[{ fieldname: "notes", fieldtype: "Small Text", label: __("Notes (optional)") }],
				({ notes }) => {
					frappe.call({
						method: "cannabis_management.credit_and_ar.api.approve_terms",
						args: { sales_order: frm.doc.name, notes },
						freeze: true,
						callback: () => frm.reload_doc(),
					});
				},
				__("Approve Terms"),
				__("Approve")
			);
		}).addClass("btn-primary");

		frm.add_custom_button(__("Reject Terms"), () => {
			frappe.prompt(
				[
					{
						fieldname: "reason",
						fieldtype: "Small Text",
						label: __("Reason"),
						reqd: 1,
					},
				],
				({ reason }) => {
					frappe.call({
						method: "cannabis_management.credit_and_ar.api.reject_terms",
						args: { sales_order: frm.doc.name, reason },
						freeze: true,
						callback: () => frm.reload_doc(),
					});
				},
				__("Reject Terms"),
				__("Reject")
			);
		});
	}
}

function render_credit_banner(frm) {
	frm.dashboard.clear_headline();

	if (frm.doc.custom_print_blocked) {
		const why =
			frm.doc.custom_approval_status === REJECTED
				? __("This Terms order was rejected: {0}", [
						frappe.utils.escape_html(frm.doc.custom_terms_rejection_reason || ""),
				  ])
				: __(
						"This Terms order is awaiting Managing Director approval. It cannot be submitted or printed until approved."
				  );
		frm.dashboard.set_headline(why, "red");
		return;
	}

	if (!is_terms(frm) || !frm.doc.customer) return;

	frappe.call({
		method: "cannabis_management.credit_and_ar.api.get_credit_summary",
		args: { customer: frm.doc.customer, sales_order: frm.doc.name },
		callback: ({ message }) => {
			if (!message) return;

			if (message.freeze_active) {
				frm.dashboard.set_headline(
					__("A company-wide credit freeze is in effect — no new terms exposure."),
					"red"
				);
				return;
			}

			if (message.blocker) {
				frm.dashboard.set_headline(message.blocker, "red");
				return;
			}

			const parts = [
				__("Available line {0} of {1}", [
					format_currency(message.available_line, frm.doc.currency),
					format_currency(message.approved_limit, frm.doc.currency),
				]),
			];
			if (message.custom_payment_score) {
				parts.push(
					__("Score {0} ({1})", [message.custom_payment_score, message.custom_score_band])
				);
			}
			if (message.custom_hold_type && message.custom_hold_type !== "None") {
				parts.push(__("On {0}", [message.custom_hold_type]));
			}

			const negative = message.available_line < frm.doc.grand_total;
			frm.dashboard.set_headline(parts.join(" · "), negative ? "orange" : "green");
		},
	});
}

function suppress_print(frm) {
	if (!frm.doc.custom_print_blocked) return;

	// Remove the menu entries rather than clearing the whole menu, so unrelated
	// actions (Links, Duplicate, Copy to Clipboard) keep working.
	["Print", "Email", "Download PDF"].forEach((label) => {
		frm.page.menu.find(`a:contains("${__(label)}")`).parent().remove();
	});

	frm.page.btn_primary && frm.page.clear_secondary_action();
}
