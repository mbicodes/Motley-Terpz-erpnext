const CREDIT_APPLICATION_ROUTE = "credit-application";

frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		add_credit_application_link(frm);

		if (frm.doc.__islocal) return;

		render_credit_banner(frm);
		add_approval_buttons(frm);
		suppress_print(frm);
	},

	custom_mode_of_payment(frm) {
		render_credit_banner(frm);
		suppress_print(frm);
	},

	customer(frm) {
		if (frm.doc.customer) render_credit_banner(frm);
	},
});

const TERMS = "Payment Terms";
const PENDING = "Pending Approval";
const APPROVED = "Approved";
const REJECTED = "Rejected";

const PRINT_BLOCKING_HOLD_STATUSES = ["Hard Hold", "Blocked"];

function is_credit_hold_blocked(frm, credit_status) {
	return (
		frm.doc.custom_mode_of_payment === TERMS &&
		PRINT_BLOCKING_HOLD_STATUSES.includes(credit_status)
	);
}

function is_terms(frm) {
	return frm.doc.custom_mode_of_payment === TERMS && frm.doc.custom_sales_order_type !== "Samples";
}

function can_approve() {
	return ["Managing Director", "Ops Manager", "System Manager"].some((role) =>
		frappe.user_roles.includes(role)
	);
}

function add_credit_application_link(frm) {
	const url = frappe.urllib.get_full_url(`/${CREDIT_APPLICATION_ROUTE}`);

	frm.add_custom_button(
		__("Open Link"),
		() => window.open(url, "_blank"),
		__("Credit Application")
	);
	frm.add_custom_button(
		__("Copy Link"),
		() => frappe.utils.copy_to_clipboard(url),
		__("Credit Application")
	);
}

function add_approval_buttons(frm) {
	if (!is_terms(frm) || frm.doc.docstatus !== 0) return;

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
		if (frm.doc.custom_approval_status === REJECTED) {
			const why = __("This Terms order was rejected: {0}", [
				frappe.utils.escape_html(frm.doc.custom_terms_rejection_reason || ""),
			]);
			frm.dashboard.set_headline(why, "red");
		}
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

			suppress_print(frm, is_credit_hold_blocked(frm, message.custom_credit_status));

			const is_exempt = message.custom_credit_status === "Policy Exempt";

			const parts = [];
			if (!is_exempt) {
				parts.push(
					__("Available line {0} of {1}", [
						format_currency(message.available_line, frm.doc.currency),
						format_currency(message.approved_limit, frm.doc.currency),
					])
				);
			}
			if (message.custom_payment_score) {
				parts.push(
					__("Score {0} ({1})", [message.custom_payment_score, message.custom_score_band])
				);
			}
			if (message.custom_hold_type && message.custom_hold_type !== "None") {
				parts.push(__("On {0}", [message.custom_hold_type]));
			}

			if (!parts.length) return;

			const negative = !is_exempt && message.available_line < frm.doc.grand_total;
			frm.dashboard.set_headline(parts.join(" · "), negative ? "orange" : "green");
		},
	});
}

function print_icon_button(frm) {
	return frm.page.wrapper.find(
		'.page-icon-group [title="Print"], .page-icon-group [data-original-title="Print"]'
	);
}

function suppress_print(frm, credit_hold_blocked) {
	const blocked =
		frm.doc.docstatus === 0 && (frm.doc.custom_print_blocked || credit_hold_blocked);

	if (!blocked) {
		if (frm.__credit_hold_print_doc) {
			frm.print_doc = frm.__credit_hold_print_doc;
			delete frm.__credit_hold_print_doc;
		}
		print_icon_button(frm).show();
		return;
	}

	["Print", "Email", "Download PDF"].forEach((label) => {
		frm.page.menu.find(`a:contains("${__(label)}")`).parent().remove();
	});

	print_icon_button(frm).hide();

	frm.page.btn_primary && frm.page.clear_secondary_action();

	if (!frm.__credit_hold_print_doc) {
		frm.__credit_hold_print_doc = frm.print_doc.bind(frm);
		frm.print_doc = function () {};
	}
}
