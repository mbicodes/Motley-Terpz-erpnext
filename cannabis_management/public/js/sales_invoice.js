frappe.listview_settings["Sales Invoice"] = {
    onload: function (listview) {
        (listview.filter_area.filter_list || [])
            .filter(f => f.fieldname === "docstatus")
            .forEach(f => f.remove());

        let current = listview.filter_area.get();
        let has_status = current.some(f => f[1] === "status");
        if (!has_status) {
            listview.filter_area.add([
                [listview.doctype, "status", "!=", "Cancelled"]
            ]);
        }
        listview.refresh();
    },
};

frappe.ui.form.on("Sales Invoice", {

    refresh: function (frm) {

        if (!frm.is_new()) {
            frm.add_custom_button(
                __("Material Transfer"),
                function () { show_material_transfer_dialog(frm); },
                __("Actions")
            );
        }

        _check_print_access(frm);
    },

    customer: function (frm) {
        _check_print_access(frm);
    },

    project: function (frm) {
        if (frm.doc.project) {
            $.each(frm.doc.items || [], function (i, item) {
                frappe.model.set_value(
                    item.doctype,
                    item.name,
                    "batch",
                    frm.doc.project
                );
            });
        }
    },

    items_add: function (frm, cdt, cdn) {
        if (frm.doc.project) {
            frappe.model.set_value(cdt, cdn, "batch", frm.doc.project);
        }
    },
});

function _check_print_access(frm) {
    if (!frm.doc.customer) return;

    if (
        frappe.user.has_role("System Manager") ||
        frappe.user.has_role("Administrator") ||
        frappe.session.user === "Administrator"
    ) {
        return;
    }

    frappe.call({
        method: "cannabis_management.api.ar_dashboard.get_customer_gl_balance",
        args: { customer: frm.doc.customer },
        callback: function (r) {
            const balance = r.message || 0;
            if (balance > 20000) {
                _hide_print_btn(frm);
                frappe.show_alert({
                    message: __(
                        "Print disabled — {0} has an outstanding balance of ${1}. " +
                        "Contact Finance or an Admin to print.",
                        [
                            frm.doc.customer,
                            parseFloat(balance).toLocaleString("en-US", {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                            }),
                        ]
                    ),
                    indicator: "orange",
                }, 7);
            }
        },
    });
}

function _hide_print_btn(frm) {
    if (frm.toolbar && frm.toolbar.print_btn) {
        frm.toolbar.print_btn.hide();
        return;
    }
    frm.page.wrapper
        .find('.page-actions button, .page-head button')
        .filter(function () {
            const lbl = ($(this).attr("data-label") || $(this).text()).toLowerCase();
            return lbl.includes("print");
        })
        .hide();
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
                method: "cannabis_management.overrides.sales_invoice_utils.create_material_transfer_from_si",
                args: {
                    sales_invoice: frm.doc.name,
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

frappe.ui.form.on('Sales Invoice', {
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

frappe.ui.form.on('Sales Invoice', {
	before_submit(frm) {
		return cannabis_management.inter_company.prompt(frm);
	},
	on_submit(frm) {
		cannabis_management.inter_company.create(frm);
	},
});

frappe.ui.form.on('Sales Invoice', {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || frm.doc.is_return || frm.doc.company !== 'Motley Terpz') return;
		const name = frm.doc.name;
		frappe
			.xcall('cannabis_management.api.undelivered_cogs.get_invoice_status', {
				sales_invoice: frm.doc.name,
			})
			.then((r) => {
				if (!r || frm.doc.name !== name) return;
				(r.entries || []).forEach((je) => {
					frm.add_custom_button(
						je.name,
						() => frappe.set_route('Form', 'Journal Entry', je.name),
						__('Undelivered COGS')
					);
				});
				if (r.entries && r.entries.length) {
					const links = r.entries
						.map((je) => `<a href="/app/journal-entry/${je.name}">${je.name}</a> (${format_currency(je.total_debit, frm.doc.company_currency)})`)
						.join(', ');
					frm.dashboard.add_comment(__('Undelivered COGS booked: {0}', [links]), 'blue', true);
				}
				if (r.can_post && r.lines) {
					frm.add_custom_button(
						__('Post COGS ({0})', [format_currency(r.to_post, frm.doc.company_currency)]),
						() =>
							frappe.confirm(
								__('Book COGS of {0} for {1} undelivered line(s)? Dr COGS / Cr Stock Adjustment. No stock is moved.', [
									format_currency(r.to_post, frm.doc.company_currency),
									r.lines,
								]),
								() =>
									frappe
										.xcall('cannabis_management.api.undelivered_cogs.post_for_invoice', {
											sales_invoice: frm.doc.name,
										})
										.then(() => frm.reload_doc())
							),
						__('Undelivered COGS')
					);
				}
			});
	},
});
