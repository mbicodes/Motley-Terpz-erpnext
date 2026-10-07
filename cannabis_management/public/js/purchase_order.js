frappe.ui.form.on("Purchase Order", {
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
frappe.ui.form.on('Purchase Order', {
	refresh(frm) {
		frm.set_query('project', () => ({}));
	},
});
