frappe.ui.form.on('Sales Order', {
	refresh(frm) {
		apply_payment_terms_restrictions(frm);
	},
	custom_mode_of_payment(frm) {
		apply_payment_terms_restrictions(frm);
	}
});

function apply_payment_terms_restrictions(frm) {
	const blocked = frm.doc.custom_mode_of_payment === 'Payment Terms';

	if (blocked && frm.doc.docstatus === 0) {
		// Show orange banner — Save still works, only Submit is blocked
		frm.set_intro(
			__('This Sales Order is on <b>Payment Terms</b> — it cannot be submitted or printed. '
				+ 'Change the Mode of Payment to <b>Cash on Delivery</b> to enable submission.'),
			'orange'
		);

		// btn_primary  = Save   (must remain visible)
		// btn_secondary = Submit (this is what we hide)
		// Use a small delay so Frappe has time to render the button
		setTimeout(() => {
			frm.page.btn_secondary && frm.page.btn_secondary.hide();
		}, 100);

		// Override the form's print method
		frm._original_print_doc = frm._original_print_doc || frm.print_doc.bind(frm);
		frm.print_doc = function () {
			frappe.msgprint({
				title: __('Print Not Allowed'),
				message: __('Sales Orders with Mode of Payment set to <b>Payment Terms</b> cannot be printed.'),
				indicator: 'orange'
			});
		};

		// Also hide the print toolbar button
		setTimeout(() => {
			frm.page.wrapper
				.find('[data-original-title="Print"], .btn-print, [title="Print"]')
				.hide();
		}, 200);

	} else {
		frm.set_intro('');

		// Restore Submit button
		setTimeout(() => {
			frm.page.btn_secondary && frm.page.btn_secondary.show();
		}, 100);

		// Restore print
		if (frm._original_print_doc) {
			frm.print_doc = frm._original_print_doc;
			delete frm._original_print_doc;
		}

		setTimeout(() => {
			frm.page.wrapper
				.find('[data-original-title="Print"], .btn-print, [title="Print"]')
				.show();
		}, 200);
	}
}
