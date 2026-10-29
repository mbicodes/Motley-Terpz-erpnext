frappe.provide('cannabis.cash_tracking');

(function () {
	var API = 'cannabis_management.cash_management.accounting_entries.';
	var SO_BUTTON = 'Open Sales Order';

	function set_sales_order_query(frm) {
		if (!frm.fields_dict.invoice_number) return;
		frm.set_query('invoice_number', function () {
			return { query: API + 'sales_order_query' };
		});
	}

	function refresh_sales_order_button(frm) {
		frm.remove_custom_button(__(SO_BUTTON));
		if (!frm.doc.invoice_number) return;

		frm.add_custom_button(__(SO_BUTTON), function () {
			var url = '/app/sales-order/' + encodeURIComponent(frm.doc.invoice_number);
			window.open(url, '_blank', 'noopener');
		}).addClass('btn-primary-light');
	}

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
		setup: function (frm) {
			set_sales_order_query(frm);
		},

		refresh: function (frm) {
			refresh_sales_order_button(frm);
			add_action_buttons(frm);
		},

		invoice_number: function (frm) {
			refresh_sales_order_button(frm);
		}
	};
})();
