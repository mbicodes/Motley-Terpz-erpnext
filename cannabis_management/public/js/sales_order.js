frappe.ui.form.on('Sales Order', {
	refresh(frm) {
		apply_payment_terms_restrictions(frm);

		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__('Conversion Entry'), function () {
				frappe.model.open_mapped_doc({
					method: 'cannabis_management.cannabis_management.doctype.conversion_entry.conversion_entry.make_conversion_entry',
					frm: frm
				});
			}, __('Create'));
		}

		if (!frm.is_new()) {
			frm.add_custom_button(
				__('Material Transfer'),
				function () { show_material_transfer_dialog(frm); },
				__('Actions')
			);
		}

		if (frm.doc.docstatus === 0 && !frm.is_new() && frappe.model.can_create('Payment Entry')) {
			frm.add_custom_button(
				__('Payment Entry'),
				function () { frm.cscript.make_payment_entry(); },
				__('Actions')
			);
		}
	},
	setup(frm) {
		frm.cscript.custom_customer = function () {
			if (!frm.doc.customer || frm.doc.docstatus !== 0) return;
			const docname = frm.doc.name;
			const customer = frm.doc.customer;
			after_party_details(frm, () => {
				if (frm.doc.name !== docname || frm.doc.customer !== customer) return;
				prompt_sales_person(frm);
			});
		};
	},
	custom_mode_of_payment(frm) {
		apply_payment_terms_restrictions(frm);
	},
	custom_approval_status(frm) {
		apply_payment_terms_restrictions(frm);
	},
	delivery_date(frm) {
		if (!frm.doc.delivery_date || !(frm.doc.items || []).length) return;
		frm.doc.items.forEach(function (row) {
			if (row.delivery_date !== frm.doc.delivery_date) {
				frappe.model.set_value(row.doctype, row.name, 'delivery_date', frm.doc.delivery_date);
			}
		});
		frm.refresh_field('items');
	}
});

function after_party_details(frm, fn, tries = 0) {
	frappe.after_ajax(() => {
		if (frm.updating_party_details && tries < 50) {
			setTimeout(() => after_party_details(frm, fn, tries + 1), 100);
			return;
		}
		fn();
	});
}

function prompt_sales_person(frm) {
	const team = (frm.doc.sales_team || []).filter((r) => r.sales_person);
	team.sort((a, b) => (b.allocated_percentage || 0) - (a.allocated_percentage || 0));
	const customer = frm.doc.customer;
	const d = new frappe.ui.Dialog({
		title: __('Sales Person'),
		fields: [
			{
				label: __('Who is the Sales Person?'),
				fieldname: 'sales_person',
				fieldtype: 'Link',
				options: 'Sales Person',
				reqd: 1,
				default: team.length ? team[0].sales_person : undefined,
				get_query: () => ({ filters: { is_group: 0, enabled: 1 } }),
			},
		],
		size: 'small',
		primary_action_label: __('Set'),
		primary_action(values) {
			apply_sales_person(frm, values.sales_person);
			d.hide();
			frappe.call({
				method: 'cannabis_management.overrides.sales_order_utils.add_sales_person_to_customer',
				args: { customer: customer, sales_person: values.sales_person },
			}).then((r) => {
				if (r.message) {
					frappe.show_alert({
						message: __('{0} added to the Sales Team of {1}', [values.sales_person, customer]),
						indicator: 'green',
					});
				}
			});
		},
	});
	d.show();
}

function apply_sales_person(frm, sales_person) {
	const rows = frm.doc.sales_team || [];
	if (rows.length === 1 && rows[0].sales_person === sales_person) return;
	frm.clear_table('sales_team');
	const row = frm.add_child('sales_team');
	row.sales_person = sales_person;
	row.allocated_percentage = 100;
	frm.refresh_field('sales_team');
}

function apply_payment_terms_restrictions(frm) {
	const is_payment_terms = frm.doc.custom_mode_of_payment === 'Payment Terms';
	const is_hoo = frappe.user_roles.includes('HOO');

	if (!is_payment_terms || frm.doc.docstatus !== 0) {
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

	if (is_hoo) {
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

frappe.ui.form.on('Sales Order', {
	refresh(frm) {
		frm.set_query('project', () => ({}));
	},
});

window.cannabis_management = window.cannabis_management || {};
if (!cannabis_management.inter_company) {
	cannabis_management.inter_company = {
		METHOD: 'cannabis_management.inter_company.',

		prompt(frm) {
			const ns = cannabis_management.inter_company;
			return new Promise((resolve, reject) => {
				frappe.call({
					method: ns.METHOD + 'is_internal_customer',
					args: { customer: frm.doc.customer },
					callback: (r) => {
						const info = (r && r.message) || {};
						if (!info.internal) {
							resolve();
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

(function () {
	const M = 'cannabis_management.credit_and_ar.customer_contact_rules.';

	function contact_required(frm) {
		return frm.doc.custom_mode_of_payment === 'Payment Terms';
	}

	function ask_contact(frm, only_if_missing) {
		const customer = frm.doc.customer;
		if (!customer || frm.doc.docstatus !== 0) return Promise.resolve();
		return frappe.call({ method: M + 'get_customer_contact', args: { customer: customer } }).then(function (r) {
			if (frm.doc.customer !== customer) return;
			const cur = r.message || {};
			frm._cm_contact_missing = !(cur.exempt || cur.reachable || cur.email || cur.phone);
			frm._cm_contact_checked = customer;
			if (cur.exempt || (only_if_missing && !frm._cm_contact_missing)) return;
			const d = new frappe.ui.Dialog({
				title: __('Contact details for {0}', [customer]),
				fields: [
					{
						fieldtype: 'HTML',
						options: `<p class="text-muted" style="margin-bottom:4px">${__('Enter this customer\'s email address or phone number (at least one). They are saved on the customer.')}</p>`,
					},
					{ fieldname: 'email', fieldtype: 'Data', options: 'Email', label: __('Email Address'), default: cur.email || '' },
					{ fieldname: 'phone', fieldtype: 'Data', options: 'Phone', label: __('Phone Number'), default: cur.phone || '' },
				],
				primary_action_label: __('Save'),
				primary_action: function (values) {
					const email = (values.email || '').trim();
					const phone = (values.phone || '').trim();
					if (!email && !phone) {
						frappe.msgprint({
							title: __('Contact details required'),
							indicator: 'red',
							message: __('Enter an email address or a phone number.'),
						});
						return;
					}
					frappe.call({
						method: M + 'save_customer_contact',
						args: { customer: customer, email: email, phone: phone },
						freeze: true,
					}).then(function (res) {
						const c = res.message || {};
						frm._cm_contact_missing = false;
						d.hide();
						if (c.contact) frm.set_value('contact_person', c.contact);
						frappe.show_alert({ message: __('Contact details saved on {0}', [customer]), indicator: 'green' });
					});
				},
			});
			d.show();
		});
	}

	function has_order_contact(frm) {
		return !!(frm.doc.contact_email || frm.doc.contact_mobile || frm.doc.contact_phone);
	}

	frappe.ui.form.on('Sales Order', {
		customer: function (frm) {
			if (contact_required(frm)) ask_contact(frm);
		},
		custom_mode_of_payment: function (frm) {
			if (contact_required(frm) && frm.doc.customer && !has_order_contact(frm)) {
				ask_contact(frm, true);
			}
		},
		refresh: function (frm) {
			if (contact_required(frm) && frm.is_new() && frm.doc.customer
				&& frm._cm_contact_checked !== frm.doc.customer && !has_order_contact(frm)) {
				ask_contact(frm, true);
			}
		},
		validate: function (frm) {
			if (!contact_required(frm)) return;
			if (!frm.doc.customer || frm.doc.docstatus !== 0 || has_order_contact(frm)) return;
			const block = function () {
				frappe.validated = false;
				frappe.show_alert({ message: __('Add the customer\'s email or phone to continue.'), indicator: 'red' });
			};
			if (frm._cm_contact_checked === frm.doc.customer) {
				if (frm._cm_contact_missing) {
					block();
					ask_contact(frm);
				}
				return;
			}
			return ask_contact(frm, true).then(function () {
				if (frm._cm_contact_missing) block();
			});
		},
	});
})();
