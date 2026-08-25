// Shared form behaviour for the two cash-tracking capture forms
// (Motley Cash Tracking / Personal Cash Tracking). Loaded via app_include_js so
// both doctype scripts can call into it — see cash_management/doctype/*/*.js.
//
// Three things live here:
//   1. "Open Sales Order" — jumps to the linked Sales Order in a new tab.
//   2. Post-submit "Actions" menu — Payment Entry / Journal Entry, built server
//      side in cash_management/accounting_entries.py.
//   3. The Sales Order picker query, whose only job is showing the order total
//      as currency ("$24,150.00") instead of a bare number.

frappe.provide('cannabis.cash_tracking');

(function () {
	var API = 'cannabis_management.cash_management.accounting_entries.';
	var SO_BUTTON = 'Open Sales Order';

	// The Sales Order link field renders its dropdown from this query so the
	// grand total in the description carries a $ sign.
	function set_sales_order_query(frm) {
		if (!frm.fields_dict.invoice_number) return;
		frm.set_query('invoice_number', function () {
			return { query: API + 'sales_order_query' };
		});
	}

	// Present whenever a Sales Order is linked, draft or submitted — opens in a
	// new tab so the half-filled cash entry is never navigated away from.
	function refresh_sales_order_button(frm) {
		frm.remove_custom_button(__(SO_BUTTON));
		if (!frm.doc.invoice_number) return;

		frm.add_custom_button(__(SO_BUTTON), function () {
			var url = '/app/sales-order/' + encodeURIComponent(frm.doc.invoice_number);
			window.open(url, '_blank', 'noopener');
		}).addClass('btn-primary-light');
	}

	// Hand off to the server builder, then route to the unsaved result. Same
	// shape as frappe.model.open_mapped_doc, but passes the source doctype so one
	// endpoint can serve both capture forms.
	function build_target(frm, method, label) {
		frappe.call({
			method: API + method,
			args: { source_doctype: frm.doctype, source_name: frm.doc.name },
			freeze: true,
			freeze_message: __('Preparing {0}...', [label]),
			callback: function (r) {
				if (!r.message) return;
				var doc = frappe.model.sync(r.message)[0];
				frappe.set_route('Form', doc.doctype, doc.name);
			}
		});
	}

	// Only after submit, and only for people who may create the target doctype —
	// so a cash tracker without Journal Entry rights is not shown a dead button.
	function add_action_buttons(frm) {
		if (frm.doc.docstatus !== 1) return;

		if (frappe.model.can_create('Payment Entry')) {
			frm.add_custom_button(__('Payment Entry'), function () {
				build_target(frm, 'make_payment_entry', __('Payment Entry'));
			}, __('Actions'));
		}

		if (frappe.model.can_create('Journal Entry')) {
			frm.add_custom_button(__('Journal Entry'), function () {
				build_target(frm, 'make_journal_entry', __('Journal Entry'));
			}, __('Actions'));
		}
	}

	cannabis.cash_tracking = {
		// Call from the doctype's setup handler.
		setup: function (frm) {
			set_sales_order_query(frm);
		},

		// Call from the doctype's refresh handler.
		refresh: function (frm) {
			refresh_sales_order_button(frm);
			add_action_buttons(frm);
		},

		// Call from the invoice_number field handler.
		invoice_number: function (frm) {
			refresh_sales_order_button(frm);
		}
	};
})();
