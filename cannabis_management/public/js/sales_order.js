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
	},
	delivery_date(frm) {
		// Propagate the header Delivery Date to every item row so the user can set
		// it once at the top instead of editing each line. Fires only on an actual
		// change of the header field (not on form load).
		if (!frm.doc.delivery_date || !(frm.doc.items || []).length) return;
		frm.doc.items.forEach(function (row) {
			if (row.delivery_date !== frm.doc.delivery_date) {
				frappe.model.set_value(row.doctype, row.name, 'delivery_date', frm.doc.delivery_date);
			}
		});
		frm.refresh_field('items');
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


// ── Project picker: no filtering ─────────────────────────────────────────────
// Core restricts Project by company, and on selling forms by customer too
// (erpnext/public/js/utils/sales_common.js, controllers/buying.js). Projects
// here are not company-scoped, so that hid valid choices. Cleared in refresh
// so it lands after core's own setup_queries, which is where core sets it.
frappe.ui.form.on('Sales Order', {
	refresh(frm) {
		frm.set_query('project', () => ({}));
	},
});


// ── Inter-company counterpart ────────────────────────────────────────────────
// A sale to an internal customer raises the matching purchase document in the
// buying company. The buying side needs a Company, Warehouse and Project that
// the sale does not carry, so they are asked for before the sale is committed.
//
// Defined behind a guard because all three selling forms ship this same block
// and only one copy needs to win. Kept out of hooks.py deliberately: these
// three files are already wired as doctype_js, so the feature ships without
// touching a shared file.
window.cannabis_management = window.cannabis_management || {};
if (!cannabis_management.inter_company) {
	cannabis_management.inter_company = {
		METHOD: 'cannabis_management.inter_company.',

		// form.js awaits before_submit, so returning a promise holds the submit
		// open until the dialog is answered. Rejecting aborts the submit.
		prompt(frm) {
			const ns = cannabis_management.inter_company;
			return new Promise((resolve, reject) => {
				frappe.call({
					method: ns.METHOD + 'is_internal_customer',
					args: { customer: frm.doc.customer },
					callback: (r) => {
						const info = (r && r.message) || {};
						if (!info.internal) {
							resolve();          // ordinary sale, nothing to raise
							return;
						}
						let answered = false;
						const d = new frappe.ui.Dialog({
							title: __('Inter-company purchase details'),
							fields: [
								{
									fieldname: 'info', fieldtype: 'HTML',
									options: `<p style="color:var(--text-muted);font-size:12px">${
										__('{0} is an internal customer, so submitting this will raise the matching purchase document.',
											[frappe.utils.escape_html(frm.doc.customer)])}</p>`,
								},
								{
									fieldname: 'company', fieldtype: 'Link', options: 'Company',
									label: __('Company (buying side)'), reqd: 1,
									default: info.represents_company,
								},
								{
									fieldname: 'warehouse', fieldtype: 'Link', options: 'Warehouse',
									label: __('Warehouse'), reqd: 1,
									get_query: () => ({ filters: { is_group: 0, disabled: 0 } }),
								},
								{
									fieldname: 'project', fieldtype: 'Link', options: 'Project',
									label: __('Project'), reqd: 1,
								},
							],
							primary_action_label: __('Continue and submit'),
							primary_action(values) {
								answered = true;
								frm.__inter_company = values;
								d.hide();
								resolve();
							},
						});
						// Closing the dialog means "don't submit".
						d.$wrapper.on('hidden.bs.modal', () => {
							if (!answered) {
								frappe.validated = false;
								reject();
							}
						});
						d.show();
					},
					error: reject,
				});
			});
		},

		// Runs after the sale is safely submitted, in its own request — a failure
		// here reports itself without undoing the sale.
		create(frm) {
			const ns = cannabis_management.inter_company;
			const values = frm.__inter_company;
			if (!values) return;
			frm.__inter_company = null;

			frappe.call({
				method: ns.METHOD + 'create_counterpart',
				args: {
					doctype: frm.doctype,
					name: frm.docname,
					company: values.company,
					warehouse: values.warehouse,
					project: values.project,
				},
				freeze: true,
				freeze_message: __('Raising the inter-company document…'),
			});
		},
	};
}

frappe.ui.form.on('Sales Order', {
	before_submit(frm) {
		return cannabis_management.inter_company.prompt(frm);
	},
	on_submit(frm) {
		cannabis_management.inter_company.create(frm);
	},
});
