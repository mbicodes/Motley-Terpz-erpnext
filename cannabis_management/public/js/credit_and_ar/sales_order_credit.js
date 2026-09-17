// Sales Order credit gate — buttons, banners and print suppression.
//
// The print suppression here is convenience only. Every print and PDF route is
// guarded server-side in credit_and_ar/print_guard.py; removing these menu
// items just stops people hitting a wall they can see coming.

// Public intake form prospects use to apply for terms — see
// credit_and_ar/web_form/credit_application/credit_application.json (route below).
const CREDIT_APPLICATION_ROUTE = "credit-application";

frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		// Always available — sales reps need to hand this link to a customer
		// regardless of the order's docstatus, so it isn't gated like the
		// approval buttons below.
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

// Credit statuses that stop a Payment Terms order from printing outright,
// independent of the Terms-approval workflow. Mirrors
// credit_and_ar/print_guard.py's _PRINT_BLOCKING_STATUSES — that server-side
// check is the real enforcement; this only keeps the UI from showing a button
// (and a Ctrl+P shortcut) that would just fail.
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

	// "Request MD Approval" removed per Finance request. Approve/Reject Terms
	// stay wired below for any order that is already Pending Approval.

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
		// The "awaiting Managing Director approval" banner is intentionally
		// suppressed here — the underlying block (before_submit / print_guard)
		// still applies, only this visual warning is hidden.
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

			// Customer-level hold, checked live off the credit summary — this is
			// what actually changes (Sales Order's own custom_print_blocked only
			// gets recomputed when the order itself is saved).
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

// The Print control shows up in two separate places in the Desk toolbar: a
// "Print" entry inside the "..." dropdown (frm.page.menu) AND a standalone
// printer icon button next to it (frm.page.wrapper > .page-icon-group,
// tagged title="Print" — see frappe/public/js/frappe/form/toolbar.js
// add_action_icon()). Hiding only the dropdown entry, as before, still left
// the icon button visible and clickable.
function print_icon_button(frm) {
	return frm.page.wrapper.find(
		'.page-icon-group [title="Print"], .page-icon-group [data-original-title="Print"]'
	);
}

function suppress_print(frm, credit_hold_blocked) {
	const blocked = frm.doc.custom_print_blocked || credit_hold_blocked;

	if (!blocked) {
		// Restore Ctrl+P / toolbar Print once a previously-held order clears
		// (e.g. the customer comes off Hard Hold and the banner refreshes).
		if (frm.__credit_hold_print_doc) {
			frm.print_doc = frm.__credit_hold_print_doc;
			delete frm.__credit_hold_print_doc;
		}
		print_icon_button(frm).show();
		return;
	}

	// Remove the menu entries rather than clearing the whole menu, so unrelated
	// actions (Links, Duplicate, Copy to Clipboard) keep working.
	["Print", "Email", "Download PDF"].forEach((label) => {
		frm.page.menu.find(`a:contains("${__(label)}")`).parent().remove();
	});

	// The standalone toolbar icon isn't inside frm.page.menu, so it survives
	// the loop above untouched unless hidden separately.
	print_icon_button(frm).hide();

	frm.page.btn_primary && frm.page.clear_secondary_action();

	// frm.print_doc backs both the toolbar Print icon and the Ctrl+P shortcut —
	// patch it to a silent no-op so the shortcut does nothing at all (no print
	// view, no message). credit_and_ar/print_guard.py still blocks the actual
	// print/PDF/email routes server-side regardless.
	if (!frm.__credit_hold_print_doc) {
		frm.__credit_hold_print_doc = frm.print_doc.bind(frm);
		frm.print_doc = function () {};
	}
}
