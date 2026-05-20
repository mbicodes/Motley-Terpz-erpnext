frappe.ui.form.on('Sales Order', {
	refresh(frm) {
		apply_payment_terms_restrictions(frm);

		// Show linked Conversion Entries in the dashboard connections section
		frm.dashboard.add_transactions([{
			label: __('Manufacturing'),
			items: ['Conversion Entry']
		}]);

		// Add "Conversion Entry" to the Create dropdown (submitted SO only)
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__('Conversion Entry'), function () {
				frappe.new_doc('Conversion Entry', {
					sales_order: frm.doc.name,
					customer: frm.doc.customer,
					company: frm.doc.company,
					posting_date: frappe.datetime.get_today()
				});
			}, __('Create'));
		}
	},
	custom_mode_of_payment(frm) {
		apply_payment_terms_restrictions(frm);
	},
	custom_approval_status(frm) {
		apply_payment_terms_restrictions(frm);
	}
});

function apply_payment_terms_restrictions(frm) {
	const is_payment_terms = frm.doc.custom_mode_of_payment === 'Payment Terms';
	const is_hoo = frappe.user_roles.includes('HOO');

	if (!is_payment_terms || frm.doc.docstatus !== 0) {
		// Not Payment Terms or already submitted/cancelled — restore everything
		frm.set_intro('');
		setTimeout(() => {
			frm.page.btn_secondary && frm.page.btn_secondary.show();
		}, 100);
		if (frm._original_print_doc) {
			frm.print_doc = frm._original_print_doc;
			delete frm._original_print_doc;
		}
		setTimeout(() => {
			frm.page.wrapper
				.find('[data-original-title="Print"], .btn-print, [title="Print"]')
				.show();
		}, 200);
		return;
	}

	// Payment Terms, draft — behaviour differs by role
	if (is_hoo) {
		// HOO can submit directly; show informational banner
		frm.set_intro(
			__('This Sales Order is on <b>Payment Terms</b>. As HOO, you can <b>Submit</b> it to approve — the creator will receive the PDF by email automatically.'),
			'blue'
		);
		setTimeout(() => {
			frm.page.btn_secondary && frm.page.btn_secondary.show();
		}, 100);
		if (frm._original_print_doc) {
			frm.print_doc = frm._original_print_doc;
			delete frm._original_print_doc;
		}
		setTimeout(() => {
			frm.page.wrapper
				.find('[data-original-title="Print"], .btn-print, [title="Print"]')
				.show();
		}, 200);
	} else {
		// Non-HOO — hide Submit and Print, show waiting message
		frm.set_intro(
			__('This Sales Order is on <b>Payment Terms</b>. Please wait for approval from the Operation Manager.'),
			'orange'
		);
		setTimeout(() => {
			frm.page.btn_secondary && frm.page.btn_secondary.hide();
		}, 100);

		frm._original_print_doc = frm._original_print_doc || frm.print_doc.bind(frm);
		frm.print_doc = function () {
			frappe.msgprint({
				title: __('Print Not Allowed'),
				message: __('This Sales Order requires approval before it can be printed.'),
				indicator: 'orange'
			});
		};

		setTimeout(() => {
			frm.page.wrapper
				.find('[data-original-title="Print"], .btn-print, [title="Print"]')
				.hide();
		}, 200);
	}
}
