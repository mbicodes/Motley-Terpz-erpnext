frappe.ui.form.on('Sales Order', {
	refresh(frm) {
		apply_payment_terms_restrictions(frm);

		// Add "Conversion Entry" to the Create dropdown (submitted SO only).
		// For the Master Touch Manufacturing company it pre-fills one row per
		// short item (ordered qty − available in the SO's Set Warehouse, or the
		// MTM Toll warehouse) as Finished Good with target = Conversion - MTM.
		// For any other company it just opens a blank Conversion Entry.
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__('Conversion Entry'), function () {
				frappe.model.open_mapped_doc({
					method: 'cannabis_management.cannabis_management.doctype.conversion_entry.conversion_entry.make_conversion_entry',
					frm: frm
				});
			}, __('Create'));
		}

		// Material Transfer action — only on saved/submitted docs
		if (!frm.is_new()) {
			frm.add_custom_button(
				__('Material Transfer'),
				function () { show_material_transfer_dialog(frm); },
				__('Actions')
			);
		}

		// Payment Entry action — draft only. Once submitted, ERPNext's own
		// "Payment" button already appears under Create, so this fills the
		// gap for drafts without duplicating it post-submit. Routes through
		// the same cscript.make_payment_entry() the core button uses, so the
		// customer is fetched onto the new Payment Entry exactly the same way.
		if (frm.doc.docstatus === 0 && !frm.is_new() && frappe.model.can_create('Payment Entry')) {
			frm.add_custom_button(
				__('Payment Entry'),
				function () { frm.cscript.make_payment_entry(); },
				__('Actions')
			);
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


// ── Material Transfer dialog ─────────────────────────────────────────

function show_material_transfer_dialog(frm) {
	let d = new frappe.ui.Dialog({
		title: __("Material Transfer"),
		fields: [
			{
				label: __("Source Warehouse"),
				fieldname: "source_warehouse",
				fieldtype: "Link",
				options: "Warehouse",
				reqd: 1,
			},
			{
				label: __("Target Warehouse"),
				fieldname: "target_warehouse",
				fieldtype: "Link",
				options: "Warehouse",
				reqd: 1,
			},
			{
				fieldtype: "HTML",
				fieldname: "info_html",
				options:
					'<p class="text-muted" style="margin-top:10px;">' +
					__(
						"Items will be transferred from the Source Warehouse to the " +
						"Target Warehouse. If an item's requested quantity exceeds " +
						"available stock, only the available quantity will be transferred."
					) +
					"</p>",
			},
		],
		size: "small",
		primary_action_label: __("Transfer"),
		primary_action(values) {
			frappe.call({
				method: "cannabis_management.overrides.sales_order_utils.create_material_transfer_from_so",
				args: {
					sales_order: frm.doc.name,
					source_warehouse: values.source_warehouse,
					target_warehouse: values.target_warehouse,
				},
				freeze: true,
				freeze_message: __("Creating Material Transfer..."),
				callback: function (r) {
					if (r.message) {
						frappe.msgprint({
							title: __("Material Transfer Created"),
							message: r.message.message,
							indicator: "green",
						});
						d.hide();
						frm.reload_doc();
					}
				},
			});
		},
	});

	d.show();
}
