// Post / Unpost on a Payment Entry or Journal Entry raised from a cash entry.
//
// The pair completes the loop that starts on the cash tracking form: submit the
// entry, use Actions to build the Payment Entry or Journal Entry, submit that,
// then Post it — which ticks "Processed" on the cash entry without anyone
// having to go back and find it. Unpost clears the tick again.
//
// Finance only: the buttons are not rendered for anyone else, and set_posted
// refuses regardless, so hiding them is convenience rather than the boundary.

frappe.provide('cannabis.cash_post');

cannabis.cash_post = {
	API: 'cannabis_management.cash_management.accounting_entries.',

	refresh: function (frm) {
		// Only a submitted voucher can be posted — before that there is nothing
		// to say the money has been recorded.
		if (frm.doc.docstatus !== 1 || !frm.doc.custom_cash_tracking_entry) return;

		frappe.call({
			method: cannabis.cash_post.API + 'get_post_state',
			args: { voucher_doctype: frm.doctype, voucher_name: frm.doc.name },
			callback: function (r) {
				var state = r.message;
				if (!state || !state.can_post) return;
				cannabis.cash_post.render(frm, state);
			}
		});
	},

	render: function (frm, state) {
		var label = state.processed ? __('Unpost') : __('Post');
		var next = state.processed ? 0 : 1;

		frm.add_custom_button(label, function () {
			frappe.call({
				method: cannabis.cash_post.API + 'set_posted',
				args: { voucher_doctype: frm.doctype, voucher_name: frm.doc.name, posted: next },
				freeze: true,
				freeze_message: next ? __('Posting...') : __('Unposting...'),
				callback: function (r) {
					if (!r.message) return;
					frappe.show_alert({
						message: next
							? __('{0} marked processed', [state.source_name])
							: __('{0} unmarked', [state.source_name]),
						indicator: next ? 'green' : 'orange'
					}, 4);
					// Redraw so the button flips to the opposite action.
					frm.clear_custom_buttons();
					frm.trigger('refresh');
				}
			});
		}, __('Actions'));

		// A quick way back to the entry being posted.
		frm.add_custom_button(__('Cash Entry'), function () {
			frappe.set_route('Form', state.source_doctype, state.source_name);
		}, __('Actions'));

		frm.dashboard.add_indicator(
			state.processed ? __('Posted to cash tracking') : __('Not posted'),
			state.processed ? 'green' : 'orange'
		);
	}
};

frappe.ui.form.on('Payment Entry', {
	refresh: function (frm) { cannabis.cash_post.refresh(frm); }
});

frappe.ui.form.on('Journal Entry', {
	refresh: function (frm) { cannabis.cash_post.refresh(frm); }
});
