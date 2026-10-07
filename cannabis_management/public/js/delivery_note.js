frappe.ui.form.on("Delivery Note", {
    refresh: function (frm) {
        // Source/Target Tags: only offer Metric Tags whose License matches
        // the row's Warehouse/Target Warehouse. Source Tags: only Active
        // tags. Target Tags: only Unused tags.
        cannabis_management.metric_tag.filter_by_warehouse(
            frm, "tags", "warehouse", "items",
            "cannabis_management.cannabis_management.custom.metric_tag.source_tags_for_warehouse"
        );
        cannabis_management.metric_tag.filter_by_warehouse(
            frm, "to_tags", "target_warehouse", "items",
            "cannabis_management.cannabis_management.custom.metric_tag.target_tags_for_warehouse"
        );

        // View > Accounting Ledger: core opens it from posting_date to the
        // note's *modified* date, which is often a different day (and can
        // even land before posting_date). The stock GL may also be filed
        // under the linked Sales Invoice on the invoice's date, so ask the
        // server which voucher and dates the entries really sit under.
        // This handler runs before the controller's refresh, which is what
        // calls show_general_ledger(), so shadowing the method here is enough.
        frm.cscript.show_general_ledger = function () {
            if (frm.doc.docstatus > 0) {
                frm.add_custom_button(__("Accounting Ledger"), function () {
                    frappe.call({
                        method: "cannabis_management.overrides.delivery_note_gl.get_accounting_ledger_route",
                        args: { delivery_note: frm.doc.name },
                    }).then((r) => {
                        const route = r.message || {};
                        frappe.route_options = {
                            voucher_no: route.voucher_no || frm.doc.name,
                            from_date: route.from_date || frm.doc.posting_date,
                            to_date: route.to_date || frm.doc.posting_date,
                            company: frm.doc.company,
                            categorize_by: "Categorize by Voucher (Consolidated)",
                            show_cancelled_entries: frm.doc.docstatus === 2,
                            ignore_prepared_report: true,
                        };
                        frappe.set_route("query-report", "General Ledger");
                    });
                }, __("View"));
            }
        };
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

// ── Project picker: no filtering ─────────────────────────────────────────────
// Core restricts Project by company, and on selling forms by customer too
// (erpnext/public/js/utils/sales_common.js, controllers/buying.js). Projects
// here are not company-scoped, so that hid valid choices. Cleared in refresh
// so it lands after core's own setup_queries, which is where core sets it.
frappe.ui.form.on('Delivery Note', {
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

frappe.ui.form.on('Delivery Note', {
	before_submit(frm) {
		return cannabis_management.inter_company.prompt(frm);
	},
	on_submit(frm) {
		cannabis_management.inter_company.create(frm);
	},
});
